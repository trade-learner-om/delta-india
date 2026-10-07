from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.config import settings
from cryptobridge.delta.rest_client import DeltaRestClient, WalletSummary
from cryptobridge.delta.wallet_margin import meta_account_equity
from cryptobridge.exceptions import http_error
from cryptobridge.utils import crypto as secret_crypto
from cryptobridge.utils.account_names import broker_display_name

SUPPORTED_EXCHANGES = ("delta",)
DEFAULT_RISK = 100.0
log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mask_api_key(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return value
    return f"{value[:4]}...{value[-4:]}"


def _normalize_exchange(value: str | None) -> str:
    exchange = str(value or "delta").strip().lower()
    if exchange not in SUPPORTED_EXCHANGES:
        raise http_error(400, f"exchange must be one of: {', '.join(SUPPORTED_EXCHANGES)}")
    return exchange


class AccountService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        delta: DeltaRestClient,
    ) -> None:
        self._accounts = db.delta_accounts
        self._users = db.app_users
        self._delta = delta

    async def list_accounts(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        cursor = self._accounts.find({"userId": user["id"]}).sort("createdAt", 1)
        results = []
        async for account in cursor:
            account["id"] = str(account["_id"])
            results.append(await self._enrich_account(account, user.get("selectedAccountId")))
        return results

    async def list_raw_accounts(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        """Return Mongo account docs without wallet enrichment (for bulk broker polling)."""
        cursor = self._accounts.find({"userId": user["id"]}).sort("createdAt", 1)
        return [doc async for doc in cursor]

    async def add_account(
        self,
        user: dict[str, Any],
        account_name: str | None,
        api_key: str,
        api_secret: str,
        exchange: str = "delta",
    ) -> dict[str, Any]:
        if not api_key or not api_secret:
            raise http_error(400, "API key and secret are required.")
        exchange = _normalize_exchange(exchange)
        now = _now()
        profile = await self._delta.fetch_profile(api_key.strip(), api_secret.strip())
        label = broker_display_name(profile.account_name or account_name, profile.id)
        doc = {
            "userId": user["id"],
            "accountName": label,
            "exchange": "delta",
            "exchangeUserId": profile.id,
            "email": profile.email,
            "apiKey": api_key.strip(),
            "encryptedApiSecret": secret_crypto.encrypt(api_secret.strip(), settings.crypto_secret),
            "riskAmount": DEFAULT_RISK,
            "createdAt": now,
            "updatedAt": now,
        }

        result = await self._accounts.insert_one(doc)
        account_id = str(result.inserted_id)
        doc["id"] = account_id
        doc["_id"] = result.inserted_id
        if not user.get("selectedAccountId"):
            await self._users.update_one(
                {"_id": ObjectId(user["id"])},
                {"$set": {"selectedAccountId": account_id, "selectedVenue": "crypto", "updatedAt": now}},
            )
            return await self._enrich_account(doc, account_id)
        return await self._enrich_account(doc, user.get("selectedAccountId"))

    async def select_account(self, user: dict[str, Any], account_id: str) -> None:
        account = await self._accounts.find_one(
            {"_id": ObjectId(account_id), "userId": user["id"]}
        )
        if not account:
            raise http_error(404, "Account not found.")
        await self._users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$set": {"selectedAccountId": account_id, "selectedVenue": "crypto", "updatedAt": _now()}},
        )

    async def delete_account(self, user: dict[str, Any], account_id: str) -> None:
        account = await self._accounts.find_one(
            {"_id": ObjectId(account_id), "userId": user["id"]}
        )
        if not account:
            raise http_error(404, "Account not found.")
        await self._accounts.delete_one({"_id": account["_id"]})
        remaining = []
        async for item in self._accounts.find({"userId": user["id"]}).sort("createdAt", 1):
            remaining.append(str(item["_id"]))
        next_selected = user.get("selectedAccountId")
        updates: dict[str, Any] = {"updatedAt": _now()}
        if next_selected == account_id:
            updates["selectedAccountId"] = remaining[0] if remaining else None
            if not remaining and str(user.get("selectedVenue") or "") == "crypto":
                updates["selectedVenue"] = None
            elif remaining:
                updates["selectedVenue"] = "crypto"
        await self._users.update_one({"_id": ObjectId(user["id"])}, {"$set": updates})

    async def update_risk(self, user: dict[str, Any], account_id: str, risk_amount: float) -> dict:
        if risk_amount <= 0:
            raise http_error(400, "Risk amount must be greater than 0.")
        account = await self._accounts.find_one(
            {"_id": ObjectId(account_id), "userId": user["id"]}
        )
        if not account:
            raise http_error(404, "Account not found.")
        await self._accounts.update_one(
            {"_id": account["_id"]},
            {"$set": {"riskAmount": risk_amount, "updatedAt": _now()}},
        )
        account["riskAmount"] = risk_amount
        account["id"] = str(account["_id"])
        return await self._enrich_account(account, user.get("selectedAccountId"))

    async def require_selected_account(self, user: dict[str, Any]) -> dict | None:
        account_id = user.get("selectedAccountId")
        if not account_id:
            return None
        return await self._accounts.find_one(
            {"_id": ObjectId(account_id), "userId": user["id"]}
        )

    async def get_account(self, user_id: str, account_id: str) -> dict | None:
        return await self._accounts.find_one(
            {"_id": ObjectId(account_id), "userId": user_id}
        )

    def credentials_for(self, account: dict) -> tuple[str, str]:
        api_key = account.get("apiKey", "")
        secret = secret_crypto.decrypt(account.get("encryptedApiSecret", ""), settings.crypto_secret)
        return api_key, secret

    async def _enrich_account(self, account: dict, selected_account_id: str | None) -> dict:
        account_id = account.get("id") or str(account["_id"])
        base = self._to_view(account, account_id == selected_account_id)
        exchange = str(account.get("exchange") or "delta").lower()
        if exchange != "delta":
            return base
        try:
            api_key, api_secret = self.credentials_for(account)
            wallet = await self._delta.fetch_wallet_balances(api_key, api_secret)
            return self._with_wallet(base, wallet)
        except Exception as exc:
            log.warning("Wallet enrichment failed for account %s: %s", account_id, exc)
            failed = dict(base)
            failed["walletError"] = str(exc)[:200]
            return failed

    def _to_view(self, account: dict, selected: bool) -> dict:
        account_id = account.get("id") or str(account["_id"])
        return {
            "id": account_id,
            "accountName": account.get("accountName", ""),
            "exchange": "delta",
            "exchangeUserId": account.get("exchangeUserId", ""),
            "email": account.get("email", ""),
            "apiKeyMasked": _mask_api_key(account.get("apiKey")),
            "selected": selected,
            "marketType": "INDIAN_CRYPTO",
            "brokerType": "DELTA",
            "riskAmount": account.get("riskAmount") if account.get("riskAmount") is not None else DEFAULT_RISK,
            "availableMargin": None,
            "balance": None,
            "netEquity": None,
            "currencyCode": "USD",
        }

    def _with_wallet(self, view: dict, wallet: WalletSummary) -> dict:
        view = dict(view)
        account_equity = meta_account_equity(
            {
                "net_equity": wallet.net_equity,
                "robo_trading_equity": wallet.robo_trading_equity,
            }
        )
        available = self.effective_available_margin(
            {
                "availableMargin": wallet.available_balance,
                "netEquity": account_equity,
            }
        )
        balance = wallet.balance
        if (balance is None or balance <= 0) and available > 0:
            balance = available
        view["availableMargin"] = available if available > 0 else wallet.available_balance
        view["balance"] = balance
        view["netEquity"] = account_equity
        view["roboTradingEquity"] = wallet.robo_trading_equity
        view["currencyCode"] = wallet.asset_symbol or "USD"
        view.pop("walletError", None)
        return view

    @staticmethod
    def effective_available_margin(account: dict) -> float:
        margin = account.get("availableMargin") or account.get("available_margin")
        if margin is not None:
            margin_value = float(margin)
            if margin_value > 0:
                return margin_value
        net_equity = account.get("netEquity") or account.get("net_equity")
        if net_equity is not None:
            net_value = float(net_equity)
            if net_value > 0:
                return net_value
        if margin is not None:
            return float(margin)
        return 0.0

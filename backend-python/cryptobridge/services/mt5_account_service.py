from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.config import settings
from cryptobridge.exceptions import http_error
from cryptobridge.services.account_service import _target_r
from cryptobridge.mt5.client import LocalMt5Error, Mt5Client
from cryptobridge.mt5.terminal_detection import find_running_terminal_paths
from cryptobridge.utils import crypto as secret_crypto
from cryptobridge.utils.account_names import broker_display_name
from cryptobridge.utils.forex_risk import calc_quantity, calc_rr
from cryptobridge.utils.order_prices import validate_order_prices

log = logging.getLogger(__name__)
DEFAULT_RISK = 100.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Mt5AccountService:
    def __init__(self, db: AsyncIOMotorDatabase, client: Mt5Client) -> None:
        self._accounts = db.mt5_accounts
        self._users = db.app_users
        self._client = client

    async def ensure_indexes(self) -> None:
        await self._accounts.create_index([("userId", 1), ("login", 1)], unique=True)

    def credentials_for(self, account: dict[str, Any]) -> dict[str, str]:
        raw = secret_crypto.decrypt(account.get("encryptedCredentials") or "", settings.crypto_secret)
        data = json.loads(raw)
        return {
            "login": str(data.get("login") or ""),
            "password": str(data.get("password") or ""),
            "server": str(data.get("server") or ""),
            "path": str(data.get("path") or ""),
        }

    async def list_raw_accounts(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        cursor = self._accounts.find({"userId": user["id"]}).sort("createdAt", 1)
        return [doc async for doc in cursor]

    def open_book(self, account: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        return self._client.open_book(self.credentials_for(account))

    async def list_accounts(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        selected = str(user.get("selectedAccountId") or "")
        venue = str(user.get("selectedVenue") or "")
        cursor = self._accounts.find({"userId": user["id"]}).sort("createdAt", 1)
        rows = []
        async for doc in cursor:
            rows.append(self._view(doc, selected=selected == str(doc["_id"]) and venue == "forex"))
        return rows

    async def add_account(
        self,
        user: dict[str, Any],
        *,
        login: str,
        password: str,
        server: str,
        terminal_path: str,
        risk_amount: float | None = None,
    ) -> dict[str, Any]:
        login = str(login or "").strip()
        server = str(server or "").strip()
        terminal_path = str(terminal_path or "").strip().strip('"')
        if not terminal_path:
            found = find_running_terminal_paths()
            if len(found) == 1:
                terminal_path = found[0]
        if not login or not password or not server or not terminal_path:
            raise http_error(400, "MT5 account number, password, server, and terminal path are required.")
        existing = await self._accounts.find_one({"userId": user["id"], "login": login})
        await self._reject_shared_terminal(user, terminal_path, exclude_id=existing.get("_id") if existing else None)
        credentials = {"login": login, "password": password, "server": server, "path": terminal_path}
        try:
            snapshot = self._client.account_snapshot(credentials)
        except LocalMt5Error as exc:
            raise http_error(400, str(exc)) from exc
        broker_text = snapshot.get("company") or snapshot.get("name") or server
        label = broker_display_name(broker_text, snapshot.get("login") or login)
        now = _now()
        doc = {
            "userId": user["id"],
            "venue": "forex",
            "accountName": label,
            "brokerName": broker_text,
            "login": str(snapshot.get("login") or login),
            "server": snapshot.get("server") or server,
            "encryptedCredentials": secret_crypto.encrypt(json.dumps(credentials), settings.crypto_secret),
            "balance": snapshot.get("balance"),
            "equity": snapshot.get("equity"),
            "currency": snapshot.get("currency") or "USD",
            "brokerUtcOffsetSeconds": int(snapshot.get("brokerUtcOffsetSeconds") or 0),
            "riskAmount": float(risk_amount) if risk_amount and risk_amount > 0 else DEFAULT_RISK,
            "createdAt": now,
            "updatedAt": now,
        }
        existing = await self._accounts.find_one({"userId": user["id"], "login": doc["login"]})
        if existing:
            await self._accounts.update_one({"_id": existing["_id"]}, {"$set": {**doc, "createdAt": existing.get("createdAt", now)}})
            doc["_id"] = existing["_id"]
        else:
            result = await self._accounts.insert_one(doc)
            doc["_id"] = result.inserted_id
        if not user.get("selectedAccountId"):
            await self.select_account(user, str(doc["_id"]))
        return self._view(doc, selected=not user.get("selectedAccountId"))

    async def select_account(self, user: dict[str, Any], account_id: str) -> None:
        account = await self._get(user, account_id)
        if not account:
            raise http_error(404, "Account not found.")
        await self._users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$set": {"selectedAccountId": account_id, "selectedVenue": "forex", "updatedAt": _now()}},
        )

    async def delete_account(self, user: dict[str, Any], account_id: str) -> None:
        account = await self._get(user, account_id)
        if not account:
            raise http_error(404, "Account not found.")
        await self._accounts.delete_one({"_id": account["_id"]})
        if str(user.get("selectedAccountId") or "") == account_id and str(user.get("selectedVenue") or "") == "forex":
            await self._users.update_one(
                {"_id": ObjectId(user["id"])},
                {"$set": {"selectedAccountId": None, "selectedVenue": None, "updatedAt": _now()}},
            )

    async def update_risk(self, user: dict[str, Any], account_id: str, risk_amount: float) -> dict[str, Any]:
        if risk_amount <= 0:
            raise http_error(400, "Risk amount must be greater than 0.")
        account = await self._get(user, account_id)
        if not account:
            raise http_error(404, "Account not found.")
        await self._accounts.update_one(
            {"_id": account["_id"]},
            {"$set": {"riskAmount": float(risk_amount), "updatedAt": _now()}},
        )
        account["riskAmount"] = float(risk_amount)
        return self._view(account, selected=str(user.get("selectedAccountId") or "") == account_id)

    async def update_target(self, user: dict[str, Any], account_id: str, target_mode: str, target_r: float | None) -> dict[str, Any]:
        mode = str(target_mode or "").strip().lower()
        if mode not in {"price", "r"}:
            raise http_error(400, "Target mode must be price or r.")
        multiple = _target_r(target_r)
        account = await self._get(user, account_id)
        if not account:
            raise http_error(404, "Account not found.")
        await self._accounts.update_one(
            {"_id": account["_id"]},
            {"$set": {"targetMode": mode, "targetR": multiple, "updatedAt": _now()}},
        )
        account["targetMode"] = mode
        account["targetR"] = multiple
        return self._view(account, selected=str(user.get("selectedAccountId") or "") == account_id)

    def search_symbols(self, account: dict[str, Any], query: str, limit: int = 40) -> list[str]:
        return self._client.search_symbols(self.credentials_for(account), query, limit)

    async def connected_account(self, user: dict[str, Any]) -> dict[str, Any] | None:
        selected = await self.selected_account(user)
        if selected:
            return selected
        return await self._accounts.find_one({"userId": user["id"]})

    async def _reject_shared_terminal(self, user: dict[str, Any], terminal_path: str, exclude_id: Any = None) -> None:
        cursor = self._accounts.find({"userId": user["id"]})
        async for doc in cursor:
            if exclude_id is not None and doc.get("_id") == exclude_id:
                continue
            try:
                saved = self.credentials_for(doc).get("path") or ""
            except Exception:
                continue
            if saved and _same_terminal_path(saved, terminal_path):
                raise http_error(
                    400,
                    "That terminal64.exe is already saved on another account. Use a separate MT5 folder.",
                )

    async def selected_account(self, user: dict[str, Any]) -> dict[str, Any] | None:
        if str(user.get("selectedVenue") or "") != "forex":
            return None
        account_id = user.get("selectedAccountId")
        if not account_id:
            return None
        return await self._get(user, str(account_id))

    async def preview(self, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        account = await self._require_selected(user)
        symbol = str(body.get("symbol") or "").strip()
        entry = float(body.get("entry") or 0)
        stop = float(body.get("stopLoss") or body.get("stop_loss") or 0)
        target = body.get("target")
        target_value = float(target) if target not in (None, "") else None
        validate_order_prices(body.get("side"), entry, stop, target_value)
        try:
            spec = self._client.symbol_spec(self.credentials_for(account), symbol)
        except LocalMt5Error as exc:
            raise http_error(400, str(exc)) from exc
        quantity = calc_quantity(
            spec.get("symbol") or symbol,
            float(account.get("riskAmount") or 0),
            entry,
            stop,
            account_currency=str(account.get("currency") or "USD"),
            contract_size=float(spec.get("contractSize") or 0) or None,
            volume_step=float(spec.get("volumeStep") or 0.01),
            volume_min=float(spec.get("volumeMin") or 0.01),
            volume_max=float(spec.get("volumeMax") or 0) or None,
        )
        if quantity <= 0:
            raise http_error(400, "Risk amount is too small for this stop distance.")
        return {
            "venue": "forex",
            "accountName": account.get("accountName"),
            "symbol": spec.get("symbol") or symbol,
            "quantity": quantity,
            "rr": calc_rr(str(body.get("side") or ""), entry, stop, target_value),
            "riskAmount": account.get("riskAmount"),
            "currency": account.get("currency") or "USD",
        }

    async def place(self, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        preview = await self.preview(user, body)
        account = await self._require_selected(user)
        payload = {
            "symbol": preview["symbol"],
            "side": body.get("side"),
            "order_type": body.get("orderType") or body.get("order_type") or "LIMIT",
            "entry": body.get("entry"),
            "stop_loss": body.get("stopLoss") or body.get("stop_loss"),
            "target": body.get("target"),
            "quantity": preview["quantity"],
        }
        try:
            placed = self._client.place_order(self.credentials_for(account), payload)
        except LocalMt5Error as exc:
            raise http_error(400, str(exc)) from exc
        return {**preview, **placed}

    async def refresh_offset(self, account: dict[str, Any]) -> int:
        try:
            snapshot = self._client.account_snapshot(self.credentials_for(account))
        except LocalMt5Error:
            return int(account.get("brokerUtcOffsetSeconds") or 0)
        offset = int(snapshot.get("brokerUtcOffsetSeconds") or 0)
        await self._accounts.update_one(
            {"_id": account["_id"]},
            {"$set": {"brokerUtcOffsetSeconds": offset, "equity": snapshot.get("equity"), "balance": snapshot.get("balance"), "updatedAt": _now()}},
        )
        return offset

    async def _require_selected(self, user: dict[str, Any]) -> dict[str, Any]:
        account = await self.selected_account(user)
        if not account:
            raise http_error(400, "Select a forex account before placing this order.")
        return account

    async def _get(self, user: dict[str, Any], account_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(account_id)
        except Exception:
            return None
        return await self._accounts.find_one({"_id": oid, "userId": user["id"]})

    @staticmethod
    def _view(doc: dict[str, Any], *, selected: bool) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "venue": "forex",
            "accountName": doc.get("accountName") or "",
            "brokerName": doc.get("brokerName") or "",
            "login": doc.get("login") or "",
            "server": doc.get("server") or "",
            "exchange": "mt5",
            "brokerType": "MT5",
            "marketType": "FOREX",
            "selected": selected,
            "riskAmount": doc.get("riskAmount") if doc.get("riskAmount") is not None else DEFAULT_RISK,
            "targetMode": doc.get("targetMode") if doc.get("targetMode") in {"price", "r"} else "price",
            "targetR": doc.get("targetR"),
            "balance": doc.get("balance"),
            "netEquity": doc.get("equity"),
            "currencyCode": doc.get("currency") or "USD",
            "brokerUtcOffsetSeconds": int(doc.get("brokerUtcOffsetSeconds") or 0),
        }


def _same_terminal_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.normpath(left.strip().strip('"'))) == os.path.normcase(
        os.path.normpath(right.strip().strip('"'))
    )

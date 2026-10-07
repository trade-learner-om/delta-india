from __future__ import annotations
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.config import settings
from cryptobridge.services.account_service import AccountService
from cryptobridge.delta.rest_client import (
    DEFAULT_BRACKET_STOP_TRIGGER,
    DeltaRestClient,
    ProductSummary,
)
from cryptobridge.exceptions import http_error
from cryptobridge.utils import crypto as secret_crypto
from cryptobridge.utils.risk_limits import assert_risk_within_cap
from cryptobridge.utils.risk_sizing import RiskSizingError, compute_position_size


class OrderService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        delta: DeltaRestClient,
        account_service: AccountService,
    ) -> None:
        self._accounts = db.delta_accounts
        self._delta = delta
        self._account_service = account_service

    async def list_active(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        account = await self._selected_account(user)
        self._ensure_delta_account(account)
        api_key, api_secret = self._credentials(account)
        orders = await self._delta.fetch_open_orders(api_key, api_secret)
        return [self._to_order_view(order) for order in orders]

    async def preview(self, user: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        account = await self._selected_account(user)
        self._ensure_delta_account(account)
        product = await self._delta.fetch_product(request["symbol"])
        entry = request.get("entry")
        stop_loss = request.get("stop_loss") or request.get("stopLoss")
        target = request.get("target")
        if entry is None or stop_loss is None:
            raise http_error(400, "Entry and stop loss are required.")
        risk_amount = float(account.get("riskAmount") or 0)
        try:
            size = compute_position_size(risk_amount, entry, stop_loss, product.contract_value)
        except RiskSizingError as exc:
            raise http_error(400, str(exc)) from exc
        risk = abs(float(entry) - float(stop_loss))
        reward = abs(float(target) - float(entry)) if target not in (None, "") else None
        return {
            "venue": "crypto",
            "accountName": account.get("accountName") or "",
            "symbol": product.symbol,
            "quantity": size,
            "rr": round(reward / risk, 2) if reward is not None and risk else None,
            "riskAmount": risk_amount,
            "currency": "USD",
        }

    async def place(self, user: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        account = await self._selected_account(user)
        self._ensure_delta_account(account)
        product = await self._delta.fetch_product(request["symbol"])
        entry = request.get("entry")
        stop_loss = request.get("stop_loss") or request.get("stopLoss")
        explicit_size = request.get("size")
        if explicit_size is not None:
            size = float(explicit_size)
            if size <= 0:
                raise http_error(400, "Size must be greater than 0.")
        else:
            if entry is None:
                raise http_error(400, "Entry price is required for position sizing.")
            if stop_loss is None:
                raise http_error(400, "Stop loss is required when size is not provided.")
            risk_amount = float(account.get("riskAmount") or 0)
            if risk_amount <= 0:
                raise http_error(400, "Risk amount is required for position sizing.")
            enriched = await self._account_service._enrich_account(
                {**account, "id": str(account["_id"])},
                user.get("selectedAccountId"),
            )
            assert_risk_within_cap(
                risk_amount,
                AccountService.effective_available_margin(enriched),
            )
            try:
                size = compute_position_size(
                    risk_amount,
                    entry,
                    stop_loss,
                    product.contract_value,
                )
            except RiskSizingError as exc:
                raise http_error(400, str(exc)) from exc

        api_key, api_secret = self._credentials(account)
        payload = self._build_delta_payload(request, product, size)
        order = await self._delta.place_order(api_key, api_secret, payload)
        return {
            "orders": [
                {
                    "account_db_id": str(account["_id"]),
                    "account_name": account.get("accountName", ""),
                    "success": True,
                    "order_id": order.id,
                    "size": size,
                    "status": order.status,
                }
            ],
            "failed_count": 0,
            "success_count": 1,
        }

    async def cancel(self, user: dict[str, Any], order_id: int) -> None:
        account = await self._selected_account(user)
        self._ensure_delta_account(account)
        api_key, api_secret = self._credentials(account)
        await self._delta.cancel_order(api_key, api_secret, order_id)

    async def _selected_account(self, user: dict[str, Any]) -> dict:
        if not user.get("selectedAccountId"):
            raise http_error(400, "Select an account before trading.")
        account = await self._accounts.find_one(
            {"_id": ObjectId(user["selectedAccountId"]), "userId": user["id"]}
        )
        if not account:
            raise http_error(404, "Account not found.")
        return account

    @staticmethod
    def _ensure_delta_account(account: dict) -> None:
        exchange = str(account.get("exchange") or "delta").lower()
        if exchange != "delta":
            raise http_error(400, "Only Delta accounts support order placement.")

    def _credentials(self, account: dict) -> tuple[str, str]:
        return (
            account.get("apiKey", ""),
            secret_crypto.decrypt(account.get("encryptedApiSecret", ""), settings.crypto_secret),
        )

    def _build_delta_payload(self, request: dict, product: ProductSummary, size: float) -> dict:
        payload: dict[str, Any] = {
            "product_id": product.product_id,
            "product_symbol": product.symbol,
            "size": size,
            "side": str(request.get("side", "")).lower(),
            "time_in_force": "gtc",
        }
        order_type = str(request.get("order_type") or request.get("orderType", "LIMIT")).upper()
        entry = request.get("entry")
        if order_type == "MARKET":
            payload["order_type"] = "market_order"
        elif order_type == "LIMIT":
            if entry is None:
                raise http_error(400, "Entry price is required for limit orders.")
            payload["order_type"] = "limit_order"
            payload["limit_price"] = str(entry)
        else:
            if entry is None:
                raise http_error(400, "Entry/trigger price is required for stop orders.")
            payload["order_type"] = "market_order"
            payload["stop_order_type"] = "stop_loss_order"
            payload["stop_price"] = str(entry)
        stop_loss = request.get("stop_loss") or request.get("stopLoss")
        target = request.get("target")
        if stop_loss and stop_loss > 0:
            payload["bracket_stop_loss_price"] = str(stop_loss)
            payload["bracket_stop_trigger_method"] = DEFAULT_BRACKET_STOP_TRIGGER
        if target and target > 0:
            payload["bracket_take_profit_price"] = str(target)
        comment = request.get("comment")
        if comment and str(comment).strip():
            payload["client_order_id"] = str(comment).strip()[:32]
        return payload

    def _to_order_view(self, order) -> dict[str, Any]:
        order_type = order.order_type or ""
        normalized = order_type.lower()
        if "market" in normalized:
            mapped_type = "MARKET"
        elif "limit" in normalized:
            mapped_type = "LIMIT"
        else:
            mapped_type = "SL"
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "order_type": mapped_type,
            "side": "SELL" if order.side.upper() == "SELL" else "BUY",
            "entry": order.limit_price if order.limit_price is not None else order.stop_price,
            "stop_loss": order.stop_loss_price,
            "target": order.take_profit_price,
            "quantity": order.size,
            "status": order.status,
            "unfilled_size": order.unfilled_size,
            "created_at": order.created_at,
        }

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.config import settings
from cryptobridge.delta.market_data import DeltaMarketDataService, LiveTicker
from cryptobridge.delta.private_stream import DeltaPrivateStreamService
from cryptobridge.delta.rest_client import DeltaRestClient, ProductSummary, normalize_order_size, normalize_symbol
from cryptobridge.exceptions import http_error
from cryptobridge.services.account_service import AccountService
from cryptobridge.utils import crypto as secret_crypto
from cryptobridge.utils.positions_helpers import delta_position_view

log = logging.getLogger(__name__)

COLLECTION = "spot_sl_monitors"

STATUS_PENDING = "Pending Trigger"
STATUS_ORDER_PLACED = "Order Placed"
STATUS_ORDER_FILLED = "Order Filled"
STATUS_SQUARED_OFF = "Squared Off"
STATUS_CANCELLED = "Cancelled"
STATUS_FAILED = "Failed"
STATUS_CLOSING = "Closing"

ACTIVE_STATUSES = {STATUS_PENDING, STATUS_ORDER_PLACED, STATUS_ORDER_FILLED, STATUS_CLOSING}
TERMINAL_STATUSES = {STATUS_SQUARED_OFF, STATUS_CANCELLED, STATUS_FAILED}

FILL_POLL_SECONDS = 5.0
SAFE_MODE_PREMIUM_MULT = 1.5


def spot_symbol_for_underlying(underlying: str) -> str:
    coin = str(underlying or "").strip().upper()
    if coin in {"BTC", "ETH"}:
        return f"{coin}USD"
    raise http_error(400, f"Unsupported underlying: {underlying}")


def trigger_price_from_ticker(ticker: LiveTicker) -> float | None:
    if ticker.last_price is not None and ticker.last_price > 0:
        return float(ticker.last_price)
    if ticker.mark_price is not None and ticker.mark_price > 0:
        return float(ticker.mark_price)
    if ticker.bid is not None and ticker.ask is not None:
        return (ticker.bid + ticker.ask) / 2.0
    if ticker.bid is not None:
        return float(ticker.bid)
    if ticker.ask is not None:
        return float(ticker.ask)
    return None


def condition_met(spot: float, level: float, operator: str) -> bool:
    op = str(operator or "gte").lower()
    if op == "lte":
        return spot <= level
    return spot >= level


def default_operators_for_option(product: ProductSummary) -> tuple[str, str]:
    contract_type = str(product.contract_type or "").lower()
    symbol = str(product.symbol or "").upper()
    is_put = "put" in contract_type or symbol.startswith("P-")
    if is_put:
        return "lte", "lte"
    return "gte", "gte"


def is_call_option(product: ProductSummary) -> bool:
    contract_type = str(product.contract_type or "").lower()
    symbol = str(product.symbol or "").upper()
    return "call" in contract_type or symbol.startswith("C-")


def monitor_to_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc.get("_id", "")),
        "accountId": doc.get("accountId"),
        "optionSymbol": doc.get("optionSymbol"),
        "underlying": doc.get("underlying"),
        "side": doc.get("side"),
        "quantityLots": doc.get("quantityLots"),
        "strikePrice": doc.get("strikePrice"),
        "expiry": doc.get("expiry"),
        "optionType": doc.get("optionType"),
        "entrySpotSymbol": doc.get("entrySpotSymbol"),
        "entrySpotLevel": doc.get("entrySpotLevel"),
        "entrySpotOperator": doc.get("entrySpotOperator"),
        "spotStopLevel": doc.get("spotStopLevel"),
        "spotStopOperator": doc.get("spotStopOperator"),
        "status": doc.get("status"),
        "positionId": doc.get("positionId"),
        "entryOrderId": doc.get("entryOrderId"),
        "closeOrderId": doc.get("closeOrderId"),
        "fillPremium": doc.get("fillPremium"),
        "safeMode": bool(doc.get("safeMode")),
        "safeModeOrderId": doc.get("safeModeOrderId"),
        "lastSpotPrice": doc.get("lastSpotPrice"),
        "error": doc.get("error"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
        "closedAt": doc.get("closedAt"),
    }


class ExecutionBroadcaster:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, user_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
        self._queues.setdefault(user_id, set()).add(queue)
        return queue

    def unsubscribe(self, user_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if user_id in self._queues:
            self._queues[user_id].discard(queue)

    async def publish(self, user_id: str, message: dict[str, Any]) -> None:
        for queue in list(self._queues.get(user_id, set())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(message)


class ExecutionEngineService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        delta: DeltaRestClient,
        accounts: AccountService,
        market: DeltaMarketDataService,
        private_stream: DeltaPrivateStreamService,
    ) -> None:
        self._db = db
        self._coll = db[COLLECTION]
        self._delta = delta
        self._accounts = accounts
        self._market = market
        self._private_stream = private_stream
        self.broadcaster = ExecutionBroadcaster()
        self._price_queue: asyncio.Queue[Any] | None = None
        self._price_task: asyncio.Task | None = None
        self._fill_task: asyncio.Task | None = None
        self._active: dict[str, dict[str, Any]] = {}
        self._placing: set[str] = set()
        self._closing: set[str] = set()
        self._market_connected = True

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def ensure_indexes(self) -> None:
        await self._coll.create_index([("userId", 1), ("status", 1), ("updatedAt", -1)])
        await self._coll.create_index([("entrySpotSymbol", 1), ("status", 1)])
        await self._coll.create_index(
            [("positionId", 1)],
            unique=True,
            partialFilterExpression={"status": STATUS_ORDER_FILLED},
            name="filled_position_unique",
        )

    async def start(self) -> None:
        self._private_stream.add_positions_listener(self._on_position_event)
        self._market.add_connection_listener(self._on_market_connection_change)
        await self._load_active_monitors()
        self._price_queue = self._market.price_broadcaster.subscribe()
        self._price_task = asyncio.create_task(self._spot_tick_loop(), name="execution-spot-ticks")
        self._fill_task = asyncio.create_task(self._fill_poll_loop(), name="execution-fill-poll")

    async def stop(self) -> None:
        if self._price_task is not None:
            self._price_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._price_task
            self._price_task = None
        if self._fill_task is not None:
            self._fill_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._fill_task
            self._fill_task = None
        if self._price_queue is not None:
            self._market.price_broadcaster.unsubscribe(self._price_queue)
            self._price_queue = None

    async def _load_active_monitors(self) -> None:
        self._active.clear()
        cursor = self._coll.find({"status": {"$in": list(ACTIVE_STATUSES)}})
        symbols: set[str] = set()
        async for doc in cursor:
            monitor_id = str(doc["_id"])
            self._active[monitor_id] = doc
            symbols.add(str(doc.get("entrySpotSymbol") or ""))
        if symbols:
            await self._market.ensure_symbols({s for s in symbols if s})

    async def list_monitors(self, user: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
        cursor = (
            self._coll.find({"userId": user["id"]})
            .sort("updatedAt", -1)
            .limit(limit)
        )
        return [monitor_to_view(doc) async for doc in cursor]

    async def search_options(self, query: str, *, limit: int = 50) -> list[dict[str, Any]]:
        q = str(query or "").strip().lower()
        products: list[ProductSummary] = []
        for underlying in ("BTC", "ETH"):
            batch = await self._delta.fetch_products_filtered(
                underlying=underlying,
                contract_types="call_options,put_options",
                states="live",
                max_pages=5,
            )
            products.extend(batch)
        if q:
            filtered = []
            for product in products:
                strike = product.strike_price
                strike_text = f"{strike:g}" if strike is not None else ""
                haystack = " ".join(
                    [
                        product.symbol.lower(),
                        str(product.underlying_asset or "").lower(),
                        strike_text,
                        str(product.contract_type or "").lower(),
                    ]
                )
                if q in haystack or any(part in haystack for part in q.split() if part):
                    filtered.append(product)
            products = filtered
        products.sort(key=lambda p: (p.strike_price or 0.0, p.symbol))
        limited = products[:limit]
        if limited:
            await self._market.ensure_symbols({product.symbol for product in limited})
        results = []
        for product in limited:
            option_type = "PE" if "put" in str(product.contract_type or "").lower() or product.symbol.startswith("P-") else "CE"
            results.append(
                {
                    "symbol": product.symbol,
                    "underlying": product.underlying_asset,
                    "strikePrice": product.strike_price,
                    "expiry": product.expiry,
                    "optionType": option_type,
                    "contractValue": product.contract_value,
                    "tickSize": product.tick_size,
                }
            )
        return results

    async def preview_trade(self, user: dict[str, Any], symbol: str, quantity_lots: int) -> dict[str, Any]:
        account = await self._selected_account(user)
        product = await self._delta.fetch_product(symbol)
        await self._market.ensure_symbols({product.symbol})
        size = normalize_order_size(float(quantity_lots))
        api_key, api_secret = self._credentials(account)
        preview = await self._delta.preview_order(
            api_key,
            api_secret,
            {
                "product_id": product.product_id,
                "product_symbol": product.symbol,
                "size": size,
                "side": "sell",
                "order_type": "market_order",
            },
        )
        enriched = await self._accounts._enrich_account(
            {**account, "id": str(account["_id"])},
            user.get("selectedAccountId"),
        )
        return {
            **preview,
            "available_margin": AccountService.effective_available_margin(enriched),
            "quantityLots": size,
            "symbol": product.symbol,
        }

    async def create_monitor(
        self,
        user: dict[str, Any],
        *,
        option_symbol: str,
        quantity_lots: int,
        entry_spot_level: float,
        spot_stop_level: float,
        entry_spot_operator: str | None = None,
        spot_stop_operator: str | None = None,
    ) -> dict[str, Any]:
        account = await self._selected_account(user)
        account_id = str(account["_id"])
        product = await self._delta.fetch_product(option_symbol)
        if quantity_lots < 1:
            raise http_error(400, "Quantity must be at least 1 lot.")
        underlying = str(product.underlying_asset or "").upper()
        if underlying not in {"BTC", "ETH"}:
            raise http_error(400, "Only BTC and ETH options are supported.")
        default_entry_op, default_stop_op = default_operators_for_option(product)
        entry_op = entry_spot_operator or default_entry_op
        stop_op = spot_stop_operator or default_stop_op
        spot_symbol = spot_symbol_for_underlying(underlying)

        existing = await self._coll.find_one(
            {
                "userId": user["id"],
                "accountId": account_id,
                "optionSymbol": product.symbol,
                "status": {"$in": list(ACTIVE_STATUSES)},
            }
        )
        if existing:
            raise http_error(409, "An active monitor already exists for this option on the selected account.")

        option_type = "PE" if not is_call_option(product) else "CE"
        now = self._now()
        doc = {
            "userId": user["id"],
            "accountId": account_id,
            "optionSymbol": product.symbol,
            "underlying": underlying,
            "side": "SELL",
            "quantityLots": int(quantity_lots),
            "strikePrice": product.strike_price,
            "expiry": product.expiry,
            "optionType": option_type,
            "entrySpotSymbol": spot_symbol,
            "entrySpotLevel": float(entry_spot_level),
            "entrySpotOperator": entry_op,
            "spotStopLevel": float(spot_stop_level),
            "spotStopOperator": stop_op,
            "status": STATUS_PENDING,
            "positionId": None,
            "entryOrderId": None,
            "closeOrderId": None,
            "fillPremium": None,
            "safeMode": False,
            "safeModeOrderId": None,
            "lastSpotPrice": None,
            "error": None,
            "createdAt": now,
            "updatedAt": now,
            "closedAt": None,
        }
        result = await self._coll.insert_one(doc)
        doc["_id"] = result.inserted_id
        monitor_id = str(result.inserted_id)
        self._active[monitor_id] = doc
        await self._market.ensure_symbols({spot_symbol, product.symbol})
        await self._broadcast_monitor(user["id"], doc)
        return monitor_to_view(doc)

    async def cancel_monitor(self, user: dict[str, Any], monitor_id: str) -> dict[str, Any]:
        doc = await self._get_owned_monitor(user, monitor_id)
        status = doc.get("status")
        if status in TERMINAL_STATUSES:
            raise http_error(400, "Monitor is already closed.")
        if status == STATUS_ORDER_FILLED:
            raise http_error(400, "Cannot cancel a filled monitor. Square off the position manually or wait for spot SL.")
        if status == STATUS_ORDER_PLACED and doc.get("entryOrderId"):
            account = await self._get_account_doc(user["id"], str(doc["accountId"]))
            if account:
                api_key, api_secret = self._credentials(account)
                with contextlib.suppress(Exception):
                    await self._delta.cancel_order(api_key, api_secret, int(doc["entryOrderId"]))
        updated = await self._set_status(doc, STATUS_CANCELLED)
        return monitor_to_view(updated)

    async def _spot_tick_loop(self) -> None:
        assert self._price_queue is not None
        try:
            while True:
                ticker = await self._price_queue.get()
                await self._handle_spot_tick(ticker)
        except asyncio.CancelledError:
            raise

    async def _handle_spot_tick(self, ticker: LiveTicker) -> None:
        symbol = str(ticker.symbol or "").upper()
        spot = trigger_price_from_ticker(ticker)
        if spot is None:
            return
        for monitor_id, doc in list(self._active.items()):
            if str(doc.get("entrySpotSymbol") or "").upper() != symbol:
                continue
            doc["lastSpotPrice"] = spot
            await self._coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"lastSpotPrice": spot, "updatedAt": self._now()}},
            )
            status = doc.get("status")
            if status == STATUS_PENDING and monitor_id not in self._placing:
                if condition_met(spot, float(doc["entrySpotLevel"]), str(doc["entrySpotOperator"])):
                    asyncio.create_task(self._place_entry_order(monitor_id))
            elif status == STATUS_ORDER_FILLED and not doc.get("safeMode") and monitor_id not in self._closing:
                if condition_met(spot, float(doc["spotStopLevel"]), str(doc["spotStopOperator"])):
                    asyncio.create_task(self._execute_spot_sl_close(monitor_id))
            user_id = str(doc.get("userId") or "")
            if user_id:
                await self._broadcast_monitor(user_id, doc)

    async def _fill_poll_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(FILL_POLL_SECONDS)
                for monitor_id, doc in list(self._active.items()):
                    if doc.get("status") == STATUS_ORDER_PLACED:
                        await self._try_detect_fill(monitor_id)
        except asyncio.CancelledError:
            raise

    async def _on_position_event(self, account_id: str) -> None:
        for monitor_id, doc in list(self._active.items()):
            if doc.get("accountId") == account_id and doc.get("status") == STATUS_ORDER_PLACED:
                await self._try_detect_fill(monitor_id)

    async def _place_entry_order(self, monitor_id: str) -> None:
        if monitor_id in self._placing:
            return
        doc = self._active.get(monitor_id)
        if not doc or doc.get("status") != STATUS_PENDING:
            return
        self._placing.add(monitor_id)
        try:
            account = await self._get_account_doc(str(doc["userId"]), str(doc["accountId"]))
            if not account:
                await self._fail_monitor(doc, "Account not found.")
                return
            product = await self._delta.fetch_product(str(doc["optionSymbol"]))
            size = normalize_order_size(float(doc["quantityLots"]))
            api_key, api_secret = self._credentials(account)
            order = await self._delta.place_order(
                api_key,
                api_secret,
                {
                    "product_id": product.product_id,
                    "product_symbol": product.symbol,
                    "size": size,
                    "side": "sell",
                    "order_type": "market_order",
                    "time_in_force": "gtc",
                },
            )
            doc["entryOrderId"] = order.id
            doc["status"] = STATUS_ORDER_PLACED
            doc["updatedAt"] = self._now()
            await self._coll.update_one(
                {"_id": doc["_id"], "status": STATUS_PENDING},
                {
                    "$set": {
                        "status": STATUS_ORDER_PLACED,
                        "entryOrderId": order.id,
                        "updatedAt": doc["updatedAt"],
                    }
                },
            )
            await self._broadcast_monitor(str(doc["userId"]), doc)
            await self._try_detect_fill(monitor_id)
        except Exception as exc:
            log.exception("Entry order failed for monitor %s", monitor_id)
            await self._fail_monitor(doc, str(exc))
        finally:
            self._placing.discard(monitor_id)

    async def _get_account_doc(self, user_id: str, account_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(account_id)
        except Exception:
            return None
        return await self._db.delta_accounts.find_one({"_id": oid, "userId": user_id})

    def _positions_for_account(self, account_id: str) -> list[dict[str, Any]]:
        state = self._private_stream.account_state(account_id)
        if state is None:
            return []
        positions, _orders = state
        return positions

    async def _try_detect_fill(self, monitor_id: str) -> None:
        doc = self._active.get(monitor_id)
        if not doc or doc.get("status") != STATUS_ORDER_PLACED:
            return
        account_id = str(doc["accountId"])
        symbol = str(doc["optionSymbol"])
        positions = self._positions_for_account(account_id)
        if not positions:
            account = await self._get_account_doc(str(doc["userId"]), account_id)
            if not account:
                return
            api_key, api_secret = self._credentials(account)
            try:
                positions = await self._delta.fetch_margined_positions(api_key, api_secret)
            except Exception:
                return
        for raw in positions:
            pos_symbol = normalize_symbol(str(raw.get("product_symbol") or raw.get("symbol") or ""))
            if pos_symbol != normalize_symbol(symbol):
                continue
            size = float(raw.get("size") or 0)
            if size >= 0:
                continue
            view = delta_position_view(raw, account_id, source="broker")
            doc["positionId"] = view["id"]
            doc["fillPremium"] = view.get("entryPrice")
            doc["status"] = STATUS_ORDER_FILLED
            doc["updatedAt"] = self._now()
            await self._coll.update_one(
                {"_id": doc["_id"], "status": STATUS_ORDER_PLACED},
                {
                    "$set": {
                        "status": STATUS_ORDER_FILLED,
                        "positionId": view["id"],
                        "fillPremium": view.get("entryPrice"),
                        "updatedAt": doc["updatedAt"],
                    }
                },
            )
            await self._broadcast_monitor(str(doc["userId"]), doc)
            return

    async def _execute_spot_sl_close(self, monitor_id: str) -> None:
        if monitor_id in self._closing:
            return
        doc = self._active.get(monitor_id)
        if not doc or doc.get("status") != STATUS_ORDER_FILLED or doc.get("safeMode"):
            return
        self._closing.add(monitor_id)
        try:
            updated = await self._coll.find_one_and_update(
                {"_id": doc["_id"], "status": STATUS_ORDER_FILLED},
                {"$set": {"status": STATUS_CLOSING, "updatedAt": self._now()}},
                return_document=True,
            )
            if not updated:
                return
            doc.update(updated)
            account = await self._get_account_doc(str(doc["userId"]), str(doc["accountId"]))
            if not account:
                await self._fail_monitor(doc, "Account not found for close.")
                return
            product = await self._delta.fetch_product(str(doc["optionSymbol"]))
            size = normalize_order_size(float(doc["quantityLots"]))
            api_key, api_secret = self._credentials(account)
            order = await self._delta.place_market_reduce(api_key, api_secret, product, "buy", size)
            doc["closeOrderId"] = order.id
            await self._coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"closeOrderId": order.id}},
            )
            await self._set_status(doc, STATUS_SQUARED_OFF)
        except Exception as exc:
            log.exception("Spot SL close failed for monitor %s", monitor_id)
            doc["status"] = STATUS_ORDER_FILLED
            await self._coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": STATUS_ORDER_FILLED, "error": str(exc), "updatedAt": self._now()}},
            )
        finally:
            self._closing.discard(monitor_id)

    async def _enter_safe_mode(self, monitor_id: str) -> None:
        doc = self._active.get(monitor_id)
        if not doc or doc.get("status") != STATUS_ORDER_FILLED or doc.get("safeMode"):
            return
        fill_premium = doc.get("fillPremium")
        if not fill_premium or float(fill_premium) <= 0:
            doc["safeMode"] = True
            await self._coll.update_one({"_id": doc["_id"]}, {"$set": {"safeMode": True, "updatedAt": self._now()}})
            await self._broadcast_monitor(str(doc["userId"]), doc)
            return
        account = await self._get_account_doc(str(doc["userId"]), str(doc["accountId"]))
        if not account:
            return
        product = await self._delta.fetch_product(str(doc["optionSymbol"]))
        size = normalize_order_size(float(doc["quantityLots"]))
        stop_price = float(fill_premium) * SAFE_MODE_PREMIUM_MULT
        api_key, api_secret = self._credentials(account)
        try:
            order = await self._delta.place_stop_order(
                api_key,
                api_secret,
                product,
                "buy",
                size,
                stop_price,
                reduce_only=True,
                client_order_id=f"cb-safe-{monitor_id[:8]}",
            )
            doc["safeMode"] = True
            doc["safeModeOrderId"] = order.id
            doc["updatedAt"] = self._now()
            await self._coll.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "safeMode": True,
                        "safeModeOrderId": order.id,
                        "updatedAt": doc["updatedAt"],
                    }
                },
            )
            await self._broadcast_monitor(str(doc["userId"]), doc)
        except Exception as exc:
            log.exception("Safe mode stop placement failed for %s", monitor_id)
            doc["error"] = str(exc)
            await self._coll.update_one({"_id": doc["_id"]}, {"$set": {"error": str(exc), "updatedAt": self._now()}})

    async def _exit_safe_mode(self, monitor_id: str) -> None:
        doc = self._active.get(monitor_id)
        if not doc or not doc.get("safeMode"):
            return
        safe_order_id = doc.get("safeModeOrderId")
        if safe_order_id:
            account = await self._get_account_doc(str(doc["userId"]), str(doc["accountId"]))
            if account:
                api_key, api_secret = self._credentials(account)
                with contextlib.suppress(Exception):
                    await self._delta.cancel_order(api_key, api_secret, int(safe_order_id))
        doc["safeMode"] = False
        doc["safeModeOrderId"] = None
        doc["updatedAt"] = self._now()
        await self._coll.update_one(
            {"_id": doc["_id"]},
            {"$set": {"safeMode": False, "safeModeOrderId": None, "updatedAt": doc["updatedAt"]}},
        )
        await self._broadcast_monitor(str(doc["userId"]), doc)

    async def _on_market_connection_change(self, connected: bool) -> None:
        if connected == self._market_connected:
            return
        self._market_connected = connected
        if not connected:
            for monitor_id, doc in list(self._active.items()):
                if doc.get("status") == STATUS_ORDER_FILLED:
                    await self._enter_safe_mode(monitor_id)
        else:
            for monitor_id, doc in list(self._active.items()):
                if doc.get("status") == STATUS_ORDER_FILLED and doc.get("safeMode"):
                    await self._exit_safe_mode(monitor_id)

    async def _set_status(self, doc: dict[str, Any], status: str) -> dict[str, Any]:
        now = self._now()
        doc["status"] = status
        doc["updatedAt"] = now
        if status in TERMINAL_STATUSES:
            doc["closedAt"] = now
            self._active.pop(str(doc["_id"]), None)
        await self._coll.update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": status, "updatedAt": now, "closedAt": doc.get("closedAt")}},
        )
        await self._broadcast_monitor(str(doc["userId"]), doc)
        return doc

    async def _fail_monitor(self, doc: dict[str, Any], error: str) -> None:
        doc["error"] = error
        await self._set_status(doc, STATUS_FAILED)

    async def _broadcast_monitor(self, user_id: str, doc: dict[str, Any]) -> None:
        payload = {
            "type": "execution_monitor",
            "topic": "execution",
            "monitor": monitor_to_view(doc),
            "monitors": await self.list_monitors({"id": user_id}),
        }
        await self.broadcaster.publish(user_id, payload)

    async def _get_owned_monitor(self, user: dict[str, Any], monitor_id: str) -> dict[str, Any]:
        try:
            oid = ObjectId(monitor_id)
        except Exception as exc:
            raise http_error(400, "Invalid monitor id.") from exc
        doc = await self._coll.find_one({"_id": oid, "userId": user["id"]})
        if not doc:
            raise http_error(404, "Monitor not found.")
        return doc

    async def _selected_account(self, user: dict[str, Any]) -> dict[str, Any]:
        if not user.get("selectedAccountId"):
            raise http_error(400, "Select an account before trading.")
        raw = await self._get_account_doc(user["id"], user["selectedAccountId"])
        if not raw:
            raise http_error(404, "Account not found.")
        return raw

    def _credentials(self, account: dict) -> tuple[str, str]:
        return (
            account.get("apiKey", ""),
            secret_crypto.decrypt(account.get("encryptedApiSecret", ""), settings.crypto_secret),
        )

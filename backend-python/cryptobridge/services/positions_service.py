from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.delta.private_stream import DeltaPrivateStreamService
from cryptobridge.delta.rest_client import DeltaRestClient
from cryptobridge.services.account_service import AccountService
from cryptobridge.utils.positions_helpers import (
    compute_open_totals,
    delta_order_view,
    delta_position_view,
    enrich_broker_position_mark,
    group_orders_by_broker,
    is_history_order_status,
    is_open_order_status,
    position_watch_symbols,
)

log = logging.getLogger(__name__)

BROADCAST_DEBOUNCE_SECONDS = 0.5
MTM_REFRESH_SECONDS = 15.0


class PositionsBroadcaster:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, user_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=16)
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


class PositionsService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        delta: DeltaRestClient,
        accounts: AccountService,
        private_stream: DeltaPrivateStreamService,
        market: DeltaMarketDataService,
    ) -> None:
        self._db = db
        self._delta = delta
        self._accounts = accounts
        self._private_stream = private_stream
        self._market = market
        self.broadcaster = PositionsBroadcaster()
        self._live_refs: dict[str, int] = {}
        self._broadcast_tasks: dict[str, asyncio.Task] = {}
        self._last_payload: dict[str, dict[str, Any]] = {}
        self._account_users: dict[str, set[str]] = {}
        self._tracked_symbols: dict[str, set[str]] = {}
        self._symbol_users: dict[str, set[str]] = {}
        self._price_queue: asyncio.Queue[Any] | None = None
        self._price_task: asyncio.Task | None = None
        self._mtm_task: asyncio.Task | None = None

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def start(self) -> None:
        self._private_stream.add_positions_listener(self._on_delta_event)
        self._price_queue = self._market.price_broadcaster.subscribe()
        self._price_task = asyncio.create_task(self._price_loop(), name="positions-price")
        self._mtm_task = asyncio.create_task(self._mtm_loop(), name="positions-mtm")

    async def stop(self) -> None:
        for task in list(self._broadcast_tasks.values()):
            task.cancel()
        self._broadcast_tasks.clear()
        if self._price_task is not None:
            self._price_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._price_task
            self._price_task = None
        if self._mtm_task is not None:
            self._mtm_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._mtm_task
            self._mtm_task = None
        if self._price_queue is not None:
            self._market.price_broadcaster.unsubscribe(self._price_queue)
            self._price_queue = None
        self._private_stream.remove_positions_listener(self._on_delta_event)
        self._tracked_symbols.clear()
        self._symbol_users.clear()

    async def attach_live_client(self, user: dict[str, Any]) -> None:
        user_id = user["id"]
        was_unattached = self._live_refs.get(user_id, 0) == 0
        self._live_refs[user_id] = self._live_refs.get(user_id, 0) + 1
        if was_unattached:
            await self._register_user_accounts(user_id, user)
        await self._coalesced_broadcast(user_id)

    async def detach_live_client(self, user_id: str) -> None:
        count = self._live_refs.get(user_id, 0)
        if count <= 0:
            return
        if count == 1:
            self._live_refs.pop(user_id, None)
        else:
            self._live_refs[user_id] = count - 1
        if self._live_refs.get(user_id, 0) == 0:
            await self._unregister_user_accounts(user_id)
            self._untrack_user_symbols(user_id)

    async def _register_user_accounts(self, user_id: str, user: dict[str, Any]) -> None:
        for doc in await self._accounts.list_raw_accounts(user):
            account_id = str(doc["_id"])
            self._account_users.setdefault(account_id, set()).add(user_id)

    async def _unregister_user_accounts(self, user_id: str) -> None:
        for account_id, users in list(self._account_users.items()):
            users.discard(user_id)
            if not users:
                del self._account_users[account_id]

    def _untrack_user_symbols(self, user_id: str) -> None:
        old = self._tracked_symbols.pop(user_id, set())
        for symbol in old:
            users = self._symbol_users.get(symbol)
            if not users:
                continue
            users.discard(user_id)
            if not users:
                self._symbol_users.pop(symbol, None)

    async def _sync_market_subscriptions(self, user_id: str, positions: list[dict[str, Any]]) -> None:
        symbols = position_watch_symbols(positions)
        old = self._tracked_symbols.get(user_id, set())
        self._tracked_symbols[user_id] = symbols
        for symbol in old - symbols:
            users = self._symbol_users.get(symbol)
            if not users:
                continue
            users.discard(user_id)
            if not users:
                self._symbol_users.pop(symbol, None)
        for symbol in symbols:
            self._symbol_users.setdefault(symbol, set()).add(user_id)
        if symbols:
            with contextlib.suppress(Exception):
                await self._market.ensure_symbols(symbols)

    def _on_delta_event(self, account_id: str) -> None:
        for user_id in list(self._account_users.get(account_id, set())):
            if self._live_refs.get(user_id, 0) > 0:
                self._schedule_broadcast(user_id)

    def _schedule_broadcast(self, user_id: str) -> None:
        if self._live_refs.get(user_id, 0) <= 0:
            return
        task = self._broadcast_tasks.get(user_id)
        if task and not task.done():
            return
        self._broadcast_tasks[user_id] = asyncio.create_task(self._coalesced_broadcast(user_id))

    async def _coalesced_broadcast(self, user_id: str) -> None:
        await asyncio.sleep(BROADCAST_DEBOUNCE_SECONDS)
        if self._live_refs.get(user_id, 0) <= 0:
            return
        user = {"id": user_id}
        try:
            payload = await self.build_open_payload(user)
            self._last_payload[user_id] = payload
            await self._sync_market_subscriptions(user_id, payload.get("openPositions") or [])
            await self.broadcaster.publish(user_id, payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("Positions broadcast failed for %s: %s", user_id, exc)

    async def _price_loop(self) -> None:
        assert self._price_queue is not None
        try:
            while True:
                ticker = await self._price_queue.get()
                symbol = str(getattr(ticker, "symbol", "") or "").upper()
                if not symbol:
                    continue
                for user_id in list(self._symbol_users.get(symbol, set())):
                    if self._live_refs.get(user_id, 0) > 0:
                        self._schedule_broadcast(user_id)
        except asyncio.CancelledError:
            pass

    async def _mtm_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(MTM_REFRESH_SECONDS)
                for account_id in list(self._account_users.keys()):
                    with contextlib.suppress(Exception):
                        await self._private_stream.refresh_account_positions(account_id)
                for user_id in list(self._live_refs.keys()):
                    if self._live_refs.get(user_id, 0) > 0:
                        self._schedule_broadcast(user_id)
        except asyncio.CancelledError:
            pass

    async def build_open_payload(self, user: dict[str, Any]) -> dict[str, Any]:
        user_id = user["id"]

        positions: list[dict[str, Any]] = []
        orders: list[dict[str, Any]] = []

        for doc in await self._accounts.list_raw_accounts(user):
            exchange = str(doc.get("exchange") or "delta").lower()
            if exchange != "delta":
                continue
            account_id = str(doc["_id"])
            try:
                account_state = self._private_stream.account_state(account_id)
                if account_state is None:
                    api_key, api_secret = self._accounts.credentials_for(doc)
                    raw_positions = await self._delta.fetch_margined_positions(api_key, api_secret)
                    raw_orders = await self._delta.fetch_open_orders(api_key, api_secret)
                else:
                    raw_positions, raw_orders = account_state
                positions.extend(self._map_delta_positions(raw_positions, account_id))
                orders.extend(self._map_delta_open_orders(raw_orders, account_id))
            except Exception as exc:  # noqa: BLE001
                log.warning("Broker fetch failed user=%s account=%s: %s", user_id, account_id, exc)

        totals = compute_open_totals(positions)
        return {
            "type": "positions",
            "openPositions": positions,
            "openOrders": orders,
            "openCount": len(positions),
            "openOrderCount": len(orders),
            **totals,
            "updatedAt": self._now().isoformat(),
        }

    def _map_delta_positions(
        self,
        rows: list[dict[str, Any]],
        account_id: str,
    ) -> list[dict[str, Any]]:
        mapped: list[dict[str, Any]] = []
        tickers = self._market.latest_tickers
        for pos in rows:
            enriched = enrich_broker_position_mark(pos, tickers)
            view = delta_position_view(
                enriched, account_id, source="broker", linked_trade_id=None, trade_type=None
            )
            if view:
                mapped.append(view)
        return mapped

    def _map_delta_open_orders(
        self, rows: list[Any], account_id: str
    ) -> list[dict[str, Any]]:
        mapped: list[dict[str, Any]] = []
        for order in rows:
            if isinstance(order, dict):
                status = str(order.get("state") or order.get("status") or "")
                if not is_open_order_status(status):
                    continue
            elif not is_open_order_status(order.status):
                continue
            mapped.append(delta_order_view(order, account_id))
        return mapped

    async def build_history_payload(
        self, user: dict[str, Any], broker_filter: str = "all"
    ) -> dict[str, Any]:
        user_id = user["id"]
        all_orders: list[dict[str, Any]] = []

        for doc in await self._accounts.list_raw_accounts(user):
            exchange = str(doc.get("exchange") or "delta").lower()
            if exchange != "delta":
                continue
            if broker_filter not in ("all", "delta"):
                continue
            account_id = str(doc["_id"])
            api_key, api_secret = self._accounts.credentials_for(doc)
            try:
                history = await self._delta.fetch_orders_history(api_key, api_secret, page_size=50)
                all_orders.extend(
                    delta_order_view(order, account_id)
                    for order in history
                    if is_history_order_status(order.status)
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Order history fetch failed user=%s account=%s: %s", user_id, account_id, exc)

        grouped = group_orders_by_broker(all_orders)
        if broker_filter != "all":
            grouped = {broker_filter: grouped.get(broker_filter, [])}
        return {
            "type": "positions_history",
            "broker": broker_filter,
            "ordersByBroker": grouped,
            "updatedAt": self._now().isoformat(),
        }

    async def refresh_user(self, user_id: str) -> dict[str, Any] | None:
        """Rebuild and broadcast open positions immediately (e.g. after calendar fills)."""
        user = {"id": user_id}
        try:
            payload = await self.build_open_payload(user)
            self._last_payload[user_id] = payload
            await self._sync_market_subscriptions(user_id, payload.get("openPositions") or [])
            if self._live_refs.get(user_id, 0) > 0:
                await self.broadcaster.publish(user_id, payload)
            return payload
        except Exception as exc:  # noqa: BLE001
            log.warning("Positions refresh failed for %s: %s", user_id, exc)
            return None

    async def get_cached_open(self, user_id: str) -> dict[str, Any] | None:
        return self._last_payload.get(user_id)

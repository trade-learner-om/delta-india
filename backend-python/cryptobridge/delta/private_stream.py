from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import websockets

from cryptobridge.config import settings
from cryptobridge.delta.rest_client import DeltaRestClient, normalize_symbol
from cryptobridge.delta.wallet_margin import WalletMarginTracker, WalletSummary, meta_account_equity
from cryptobridge.services.account_service import AccountService
from cryptobridge.utils.signing import sign_delta_ws_auth

log = logging.getLogger(__name__)

REST_REFRESH_MIN_INTERVAL_SEC = 30.0
WS_RECONNECT_BASE_SEC = 2.0
WS_RECONNECT_MAX_SEC = 30.0
PRIVATE_WS_PING_INTERVAL_SEC = 25.0

_PRIVATE_SUBSCRIBE_CHANNELS = [
    {"name": "margins"},
    {"name": "positions", "symbols": ["all"]},
    {"name": "orders", "symbols": ["all"]},
]

_CLOSED_ORDER_STATES = frozenset({
    "CLOSED", "CANCELLED", "CANCELED", "FILLED", "REJECTED", "EXPIRED",
})


def _parse_float_size(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_symbol(row: dict[str, Any]) -> str:
    return normalize_symbol(str(row.get("product_symbol") or row.get("symbol") or ""))


def _position_rows_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    action = str(message.get("action") or "").lower()
    if action == "snapshot":
        result = message.get("result")
        if isinstance(result, list):
            return [row for row in result if isinstance(row, dict)]
        return []
    payload = message.get("positions")
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if message.get("symbol") or message.get("product_symbol"):
        return [message]
    if isinstance(payload, dict):
        return [payload]
    return []


def _apply_position_row(
    stream: _AccountStream,
    row: dict[str, Any],
    *,
    message_action: str,
) -> bool:
    symbol = _position_symbol(row)
    if not symbol:
        return False
    row_action = str(row.get("action") or message_action or "").lower()
    if row_action == "delete":
        stream.positions.pop(symbol, None)
        return True
    numeric_size = _parse_float_size(row.get("size"))
    if numeric_size == 0:
        stream.positions.pop(symbol, None)
        return True
    if numeric_size is None:
        if symbol not in stream.positions:
            return False
        previous = stream.positions[symbol]
        merged = dict(previous)
        merged.update(row)
        stream.positions[symbol] = merged
        return True
    previous = stream.positions.get(symbol, {})
    merged = dict(previous)
    merged.update(row)
    stream.positions[symbol] = merged
    return True


def _order_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("order_id") or "")


def _order_rows_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    action = str(message.get("action") or "").lower()
    if action == "snapshot":
        result = message.get("result")
        if isinstance(result, list):
            return [row for row in result if isinstance(row, dict)]
        return []
    payload = message.get("orders")
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if _order_id(message):
        return [message]
    if isinstance(payload, dict):
        return [payload]
    return []


def _orders_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        oid = _order_id(row)
        if not oid:
            continue
        status = str(row.get("state") or row.get("status") or "").upper()
        action = str(row.get("action") or "").lower()
        if action == "delete" or status in _CLOSED_ORDER_STATES:
            continue
        mapped[oid] = row
    return mapped


def _positions_map_from_rest(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build the in-memory positions cache from REST rows (non-zero size only)."""
    mapped: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = normalize_symbol(str(item.get("product_symbol") or item.get("symbol") or ""))
        if not symbol:
            continue
        try:
            size = float(item.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if size != 0:
            mapped[symbol] = item
    return mapped


class MarginBroadcaster:
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
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass


def margin_message(
    account_id: str,
    summary: WalletSummary,
    *,
    wallet_error: str | None = None,
) -> dict[str, Any]:
    from cryptobridge.services.account_service import AccountService

    available = AccountService.effective_available_margin(
        {
            "availableMargin": summary.available_balance,
            "netEquity": meta_account_equity(
                {
                    "net_equity": summary.net_equity,
                    "robo_trading_equity": summary.robo_trading_equity,
                }
            ),
        }
    )
    balance = summary.balance
    if balance <= 0 and available > 0:
        balance = available
    account_equity = meta_account_equity(
        {
            "net_equity": summary.net_equity,
            "robo_trading_equity": summary.robo_trading_equity,
        }
    )
    payload: dict[str, Any] = {
        "type": "margin",
        "account_id": account_id,
        "available_margin": available if available > 0 else summary.available_balance,
        "balance": balance,
        "net_equity": account_equity,
        "robo_trading_equity": summary.robo_trading_equity,
        "currency_code": summary.asset_symbol or "USD",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if wallet_error:
        payload["wallet_error"] = wallet_error[:200]
    return payload


@dataclass
class _AccountStream:
    account_id: str
    api_key: str
    api_secret: str
    user_ids: set[str] = field(default_factory=set)
    tracker: WalletMarginTracker = field(default_factory=WalletMarginTracker.empty)
    task: asyncio.Task | None = None
    status: str = "idle"
    last_error: str | None = None
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_rest_refresh_at: float = 0.0
    rest_refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def start(self, service: DeltaPrivateStreamService) -> None:
        if self.task and not self.task.done():
            return
        self.task = asyncio.create_task(self._run(service))

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def bootstrap_from_rest(self, delta: DeltaRestClient, service: DeltaPrivateStreamService) -> None:
        try:
            node = await delta.fetch_wallet_balances_payload(self.api_key, self.api_secret)
            self.tracker.load_wallet_payload(node)
            if self.tracker.has_margin_data():
                await service._publish_stream(self)
        except Exception as exc:
            log.warning("REST wallet bootstrap failed for account %s: %s", self.account_id, exc)
        try:
            positions = await delta.fetch_margined_positions(self.api_key, self.api_secret)
            self.positions = _positions_map_from_rest(positions)
        except Exception as exc:
            log.warning("REST positions bootstrap failed for account %s: %s", self.account_id, exc)
        try:
            orders = await delta.fetch_open_orders(self.api_key, self.api_secret)
            self.orders = {
                str(getattr(item, "id", "")): {
                    "id": getattr(item, "id", None),
                    "product_symbol": getattr(item, "symbol", None),
                    "side": getattr(item, "side", None),
                    "order_type": getattr(item, "order_type", None),
                    "status": getattr(item, "status", None),
                    "limit_price": getattr(item, "limit_price", None),
                    "stop_price": getattr(item, "stop_price", None),
                    "size": getattr(item, "size", None),
                    "unfilled_size": getattr(item, "unfilled_size", None),
                    "reduce_only": getattr(item, "reduce_only", None),
                    "created_at": getattr(item, "created_at", None),
                    "client_order_id": getattr(item, "client_order_id", None),
                }
                for item in orders
                if getattr(item, "id", None) is not None
            }
        except Exception as exc:
            log.warning("REST orders bootstrap failed for account %s: %s", self.account_id, exc)

    async def refresh_broker_state_from_rest(self, delta: DeltaRestClient) -> None:
        """Refresh positions and open orders from REST (e.g. after WS reconnect)."""
        try:
            positions = await delta.fetch_margined_positions(self.api_key, self.api_secret)
            self.positions = _positions_map_from_rest(positions)
            self.last_rest_refresh_at = time.monotonic()
        except Exception as exc:
            log.warning("REST positions refresh failed for account %s: %s", self.account_id, exc)
        try:
            orders = await delta.fetch_open_orders(self.api_key, self.api_secret)
            self.orders = {
                str(getattr(item, "id", "")): {
                    "id": getattr(item, "id", None),
                    "product_symbol": getattr(item, "symbol", None),
                    "side": getattr(item, "side", None),
                    "order_type": getattr(item, "order_type", None),
                    "status": getattr(item, "status", None),
                    "limit_price": getattr(item, "limit_price", None),
                    "stop_price": getattr(item, "stop_price", None),
                    "size": getattr(item, "size", None),
                    "unfilled_size": getattr(item, "unfilled_size", None),
                    "reduce_only": getattr(item, "reduce_only", None),
                    "created_at": getattr(item, "created_at", None),
                    "client_order_id": getattr(item, "client_order_id", None),
                }
                for item in orders
                if getattr(item, "id", None) is not None
            }
        except Exception as exc:
            log.warning("REST orders refresh failed for account %s: %s", self.account_id, exc)

    def should_skip_rest_refresh(self, *, force: bool) -> bool:
        if force:
            return False
        if self.status != "subscribed":
            return False
        elapsed = time.monotonic() - self.last_rest_refresh_at
        return self.last_rest_refresh_at > 0 and elapsed < REST_REFRESH_MIN_INTERVAL_SEC

    async def _ws_send(self, ws: Any, payload: str) -> None:
        async with self.send_lock:
            await ws.send(payload)

    async def _ws_ping_loop(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(PRIVATE_WS_PING_INTERVAL_SEC)
            try:
                await self._ws_send(ws, json.dumps({"type": "ping"}))
            except Exception:
                break

    async def _run(self, service: DeltaPrivateStreamService) -> None:
        reconnect_delay = WS_RECONNECT_BASE_SEC
        while self.user_ids:
            try:
                self.status = "connecting"
                async with websockets.connect(
                    settings.delta_private_ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=10,
                    additional_headers={"User-Agent": settings.user_agent},
                ) as ws:
                    ping_task = asyncio.create_task(self._ws_ping_loop(ws))
                    try:
                        self.status = "authenticating"
                        await self._ws_send(ws, json.dumps({"type": "enable_heartbeat"}))
                        timestamp = str(int(time.time()))
                        await self._ws_send(
                            ws,
                            json.dumps(
                                {
                                    "type": "key-auth",
                                    "payload": {
                                        "api-key": self.api_key,
                                        "signature": sign_delta_ws_auth(self.api_secret, timestamp),
                                        "timestamp": timestamp,
                                    },
                                }
                            ),
                        )
                        authenticated = False
                        async for raw in ws:
                            if not self.user_ids:
                                break
                            message = json.loads(raw)
                            msg_type = message.get("type")
                            if msg_type in ("heartbeat", "pong", "subscriptions", "success"):
                                continue
                            if msg_type == "key-auth":
                                if message.get("success"):
                                    reconnect_delay = WS_RECONNECT_BASE_SEC
                                    authenticated = True
                                    self.status = "subscribed"
                                    self.last_error = None
                                    await self._ws_send(
                                        ws,
                                        json.dumps(
                                            {
                                                "type": "subscribe",
                                                "payload": {"channels": _PRIVATE_SUBSCRIBE_CHANNELS},
                                            }
                                        ),
                                    )
                                    with contextlib.suppress(Exception):
                                        await self.refresh_broker_state_from_rest(service._delta)
                                        await service._notify_positions_listener(self.account_id)
                                else:
                                    self.last_error = str(
                                        message.get("message") or message.get("status") or "Authentication failed"
                                    )
                                    self.status = "auth_failed"
                                    await service._publish_error(self, self.last_error)
                                    return
                                continue
                            if not authenticated:
                                continue
                            if msg_type == "margins":
                                self.tracker.apply_margin_message(message)
                                if self.tracker.has_margin_data():
                                    await service._publish_stream(self)
                                continue
                            if msg_type == "positions":
                                await service._handle_positions_message(self, message)
                                continue
                            if msg_type == "orders":
                                await service._handle_orders_message(self, message)
                                continue
                    finally:
                        ping_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await ping_task
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.status = "errored"
                self.last_error = str(exc)[:200]
                log.warning("Delta private WS error for account %s: %s", self.account_id, exc)
                await service._publish_error(self, self.last_error)
            if not self.user_ids:
                break
            log.info(
                "Delta private WS reconnecting account %s in %.0fs",
                self.account_id,
                reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, WS_RECONNECT_MAX_SEC)


class DeltaPrivateStreamService:
    def __init__(self, account_service: AccountService, delta: DeltaRestClient) -> None:
        self._accounts = account_service
        self._delta = delta
        self.broadcaster = MarginBroadcaster()
        self._streams: dict[str, _AccountStream] = {}
        self._user_accounts: dict[str, set[str]] = {}
        self._live_refs: dict[str, int] = {}
        self._positions_listeners: set[Callable[[str], Awaitable[None] | None]] = set()

    def set_positions_listener(
        self, listener: Callable[[str], Awaitable[None] | None] | None
    ) -> None:
        self._positions_listeners.clear()
        if listener is not None:
            self._positions_listeners.add(listener)

    def add_positions_listener(
        self, listener: Callable[[str], Awaitable[None] | None]
    ) -> None:
        self._positions_listeners.add(listener)

    def remove_positions_listener(
        self, listener: Callable[[str], Awaitable[None] | None]
    ) -> None:
        self._positions_listeners.discard(listener)

    def _total_refs(self, user_id: str) -> int:
        return self._live_refs.get(user_id, 0)

    async def attach_live_client(self, user: dict[str, Any]) -> None:
        user_id = user["id"]
        was_unattached = self._total_refs(user_id) == 0
        self._live_refs[user_id] = self._live_refs.get(user_id, 0) + 1
        if was_unattached:
            await self.attach_user_all_delta_accounts(user)

    async def detach_live_client(self, user_id: str) -> None:
        count = self._live_refs.get(user_id, 0)
        if count <= 0:
            return
        if count == 1:
            self._live_refs.pop(user_id, None)
        else:
            self._live_refs[user_id] = count - 1
        if self._total_refs(user_id) == 0:
            await self.detach_user(user_id)

    async def stop(self) -> None:
        streams = list(self._streams.values())
        self._streams.clear()
        self._user_accounts.clear()
        self._live_refs.clear()
        for stream in streams:
            await stream.stop()

    async def _remove_user_from_account_stream(self, user_id: str, account_id: str) -> None:
        stream = self._streams.get(account_id)
        if not stream:
            return
        stream.user_ids.discard(user_id)
        if not stream.user_ids:
            await stream.stop()
            del self._streams[account_id]

    async def attach_user(self, user: dict[str, Any]) -> None:
        """Attach the user's selected Delta account (legacy margin stream)."""
        account = await self._accounts.require_selected_account(user)
        if not account:
            return
        await self._attach_account_for_user(user["id"], account)

    async def attach_user_all_delta_accounts(self, user: dict[str, Any]) -> None:
        """Attach every Delta account for the user (positions/orders/margins)."""
        user_id = user["id"]
        account_ids: set[str] = set()
        for doc in await self._accounts.list_raw_accounts(user):
            if str(doc.get("exchange") or "delta").lower() != "delta":
                continue
            await self._attach_account_for_user(user_id, doc)
            account_ids.add(str(doc["_id"]))
        if account_ids:
            self._user_accounts[user_id] = account_ids

    async def detach_user_all_delta_accounts(self, user_id: str) -> None:
        account_ids = self._user_accounts.pop(user_id, set())
        for account_id in account_ids:
            await self._remove_user_from_account_stream(user_id, account_id)

    async def _attach_account_for_user(self, user_id: str, account: dict[str, Any]) -> None:
        account_id = str(account["_id"])
        api_key, api_secret = self._accounts.credentials_for(account)

        stream = self._streams.get(account_id)
        if stream and (stream.api_key != api_key or stream.api_secret != api_secret):
            await stream.stop()
            del self._streams[account_id]
            stream = None

        if account_id not in self._streams:
            stream = _AccountStream(
                account_id=account_id,
                api_key=api_key,
                api_secret=api_secret,
            )
            self._streams[account_id] = stream
            await stream.bootstrap_from_rest(self._delta, self)
            stream.start(self)
        else:
            stream = self._streams[account_id]

        stream.user_ids.add(user_id)
        self._user_accounts.setdefault(user_id, set()).add(account_id)
        if stream.tracker.has_margin_data():
            await self._publish_stream(stream)
        elif stream.last_error:
            await self._publish_error(stream, stream.last_error)

    async def detach_user(self, user_id: str) -> None:
        account_ids = list(self._user_accounts.pop(user_id, set()))
        for account_id in account_ids:
            await self._remove_user_from_account_stream(user_id, account_id)

    async def _handle_positions_message(self, stream: _AccountStream, message: dict) -> None:
        action = str(message.get("action") or "").lower()
        if action == "snapshot":
            result = message.get("result")
            if isinstance(result, list):
                stream.positions = _positions_map_from_rest(result)
                await self._notify_positions_listener(stream.account_id)
            return

        changed = False
        for row in _position_rows_from_message(message):
            if _apply_position_row(stream, row, message_action=action):
                changed = True
        if changed:
            await self._notify_positions_listener(stream.account_id)

    async def _handle_orders_message(self, stream: _AccountStream, message: dict) -> None:
        action = str(message.get("action") or "").lower()
        if action == "snapshot":
            result = message.get("result")
            if isinstance(result, list):
                stream.orders = _orders_map_from_rows(result)
                await self._notify_positions_listener(stream.account_id)
            return

        changed = False
        for row in _order_rows_from_message(message):
            oid = _order_id(row)
            if not oid:
                continue
            row_action = str(row.get("action") or action or "").lower()
            status = str(row.get("state") or row.get("status") or "").upper()
            if row_action == "delete" or status in _CLOSED_ORDER_STATES:
                if oid in stream.orders:
                    stream.orders.pop(oid, None)
                    changed = True
            else:
                stream.orders[oid] = row
                changed = True
        if changed:
            await self._notify_positions_listener(stream.account_id)

    async def _notify_positions_listener(self, account_id: str) -> None:
        listeners = list(self._positions_listeners)
        if not listeners:
            return
        for listener in listeners:
            try:
                result = listener(account_id)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                log.debug("Positions listener failed for %s: %s", account_id, exc)

    async def refresh_for_user(self, user: dict[str, Any]) -> None:
        if self._total_refs(user["id"]) <= 0:
            return
        await self.attach_user(user)

    def account_state(self, account_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
        stream = self._streams.get(account_id)
        if stream is None:
            return None
        return list(stream.positions.values()), list(stream.orders.values())

    async def refresh_account_positions(self, account_id: str, *, force: bool = False) -> None:
        """Re-fetch open positions and orders from REST and notify listeners."""
        stream = self._streams.get(account_id)
        if stream is None:
            return
        if stream.should_skip_rest_refresh(force=force):
            return
        async with stream.rest_refresh_lock:
            if stream.should_skip_rest_refresh(force=force):
                return
            try:
                await stream.refresh_broker_state_from_rest(self._delta)
                await self._notify_positions_listener(account_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("REST broker refresh failed for account %s: %s", account_id, exc)

    async def _publish_stream(self, stream: _AccountStream) -> None:
        if not stream.tracker.has_margin_data():
            return
        summary = stream.tracker.summary()
        account_equity = meta_account_equity(
            {
                "net_equity": summary.net_equity,
                "robo_trading_equity": summary.robo_trading_equity,
            }
        )
        if summary.available_balance <= 0 and not (account_equity and account_equity > 0):
            return
        for user_id in list(stream.user_ids):
            await self.broadcaster.publish(user_id, margin_message(stream.account_id, summary))

    async def _publish_error(self, stream: _AccountStream, error: str) -> None:
        summary = stream.tracker.summary()
        for user_id in list(stream.user_ids):
            await self.broadcaster.publish(
                user_id,
                margin_message(stream.account_id, summary, wallet_error=error),
            )

from __future__ import annotations
import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import websockets

from cryptobridge.config import settings

log = logging.getLogger(__name__)

BASELINE_SYMBOLS = frozenset({"BTCUSD", "ETHUSD", "SOLUSD"})
WS_RECONNECT_BASE_SEC = 2.0
WS_RECONNECT_MAX_SEC = 30.0
MARKET_WS_PING_INTERVAL_SEC = 25.0


@dataclass
class LiveTicker:
    symbol: str
    last_price: float | None
    mark_price: float | None
    bid: float | None
    ask: float | None
    change_24h: float | None
    updated_at: datetime
    price_digits: int | None = None


def _parse_json_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        return float(text) if text else None
    except ValueError:
        return None


class LivePriceBroadcaster:
    """Dedicated broadcaster for public market ticks — separate from session/margin feeds."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[LiveTicker]] = set()

    def subscribe(self) -> asyncio.Queue[LiveTicker]:
        queue: asyncio.Queue[LiveTicker] = asyncio.Queue(maxsize=512)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[LiveTicker]) -> None:
        self._queues.discard(queue)

    async def publish(self, ticker: LiveTicker) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(ticker)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(ticker)
                except asyncio.QueueFull:
                    pass


class DeltaMarketDataService:
    def __init__(self) -> None:
        self.latest_tickers: dict[str, LiveTicker] = {}
        self.price_broadcaster = LivePriceBroadcaster()
        self.broadcaster = self.price_broadcaster
        self.status = "Disconnected"
        self.socket_connected = False
        self.last_market_event_at: datetime | None = None
        self.desired_symbols: set[str] = set()
        self._pinned_symbols: set[str] = set()
        self._ws: Any = None
        self._task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._lock = asyncio.Lock()
        self._connection_listeners: list[Callable[[bool], Awaitable[None] | None]] = []
        self._was_connected = False

    def add_connection_listener(self, listener: Callable[[bool], Awaitable[None] | None]) -> None:
        self._connection_listeners.append(listener)

    async def _notify_connection_listeners(self, connected: bool) -> None:
        for listener in list(self._connection_listeners):
            try:
                result = listener(connected)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                log.debug("Market connection listener failed: %s", exc)

    async def _ws_send(self, payload: str) -> None:
        if not self._ws:
            return
        async with self._send_lock:
            if self._ws:
                await self._ws.send(payload)

    async def start(self) -> None:
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        await self.ensure_symbols(set(BASELINE_SYMBOLS))

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()
        self._ws = None
        self.socket_connected = False

    def subscribed_symbols(self) -> list[str]:
        return sorted(self.desired_symbols)

    async def ensure_symbols(self, symbols: set[str]) -> None:
        normalized = {str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()}
        normalized.update(BASELINE_SYMBOLS)
        if not normalized:
            normalized = set(BASELINE_SYMBOLS)
        self._pinned_symbols.update(normalized)
        await self.refresh_subscriptions()

    async def add_symbols(self, symbols: set[str]) -> None:
        await self.ensure_symbols(symbols)

    async def refresh_subscriptions(self) -> None:
        symbols = set(BASELINE_SYMBOLS)
        symbols.update(self._pinned_symbols)
        async with self._lock:
            await self._apply_subscription_delta(symbols)

    def seed_ticker(self, ticker: LiveTicker) -> None:
        self._store_ticker(ticker)
        try:
            asyncio.get_running_loop().create_task(self.price_broadcaster.publish(ticker))
        except RuntimeError:
            pass

    async def _apply_subscription_delta(self, target: set[str]) -> None:
        normalized = {s.strip().upper() for s in target if s.strip()}
        normalized.update(BASELINE_SYMBOLS)
        if normalized == self.desired_symbols:
            return
        await self._ensure_connected()
        to_add = sorted(normalized - self.desired_symbols)
        to_remove = sorted((self.desired_symbols - normalized) - BASELINE_SYMBOLS)
        if to_remove and self._ws:
            await self._send_subscription("unsubscribe", to_remove)
        self.desired_symbols = normalized
        if to_add:
            if not self._ws and not await self._wait_for_ws():
                self.status = "Connecting"
                return
            if self._ws:
                await self._send_subscription("subscribe", to_add)
            self.status = "Subscribed"
        elif self.desired_symbols:
            self.status = "Subscribed" if self.socket_connected else "Connecting"
        else:
            self.status = "Connected" if self.socket_connected else "Disconnected"

    async def _ensure_connected(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_connection())

    async def _wait_for_ws(self, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._ws is not None:
                return True
            await asyncio.sleep(0.05)
        return False

    async def _run_connection(self) -> None:
        reconnect_delay = WS_RECONNECT_BASE_SEC
        while True:
            try:
                self.status = "Connecting"
                async with websockets.connect(
                    settings.delta_public_ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=10,
                ) as ws:
                    reconnect_delay = WS_RECONNECT_BASE_SEC
                    self._ws = ws
                    self.socket_connected = True
                    if not self._was_connected:
                        self._was_connected = True
                        await self._notify_connection_listeners(True)
                    self.status = "Subscribed" if self.desired_symbols else "Connected"
                    await self._ws_send(json.dumps({"type": "enable_heartbeat"}))
                    if self.desired_symbols:
                        await self._send_subscription("subscribe", sorted(self.desired_symbols))
                    async for message in ws:
                        await self._process_message(message)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("Delta market WS error: %s", exc)
                self.status = "Errored"
            finally:
                was_connected = self.socket_connected
                self._ws = None
                self.socket_connected = False
                self.status = "Disconnected"
                if was_connected:
                    self._was_connected = False
                    await self._notify_connection_listeners(False)
            if not self.desired_symbols:
                break
            log.info("Delta market WS reconnecting in %.0fs", reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, WS_RECONNECT_MAX_SEC)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(MARKET_WS_PING_INTERVAL_SEC)
            if self._ws:
                try:
                    await self._ws_send(json.dumps({"type": "ping"}))
                except Exception:
                    pass
            elif self.desired_symbols:
                await self._ensure_connected()

    async def _send_subscription(self, sub_type: str, symbols: list[str]) -> None:
        if not self._ws or not symbols:
            return
        mark_symbols = [f"MARK:{symbol}" for symbol in symbols]
        channels: list[dict[str, Any]] = [
            {"name": "ticker", "symbols": symbols},
            {"name": "ob_l1", "symbols": symbols},
            {"name": "mark_price", "symbols": mark_symbols},
        ]
        payload = {"type": sub_type, "payload": {"channels": channels}}
        await self._ws_send(json.dumps(payload))

    async def _process_message(self, message: str | bytes) -> None:
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            node = json.loads(message)
            msg_type = node.get("type", "")
            if msg_type in ("heartbeat", "pong", "subscriptions", "success"):
                self.last_market_event_at = datetime.now(timezone.utc)
                return
            if msg_type == "ob_l1":
                await self._process_ob_l1(node)
                return
            if msg_type == "mark_price":
                await self._process_mark_price(node)
                return
            if msg_type != "ticker":
                return
            details = node.get("d")
            if isinstance(details, list) and details:
                first = details[0]
            elif isinstance(details, dict):
                first = details
            else:
                first = {}
            quotes = first.get("q") or []
            symbol = str(node.get("sy") or first.get("s") or "").upper()
            if not symbol:
                return
            ohlc = first.get("ohlc") or []
            last_price = _parse_json_number(ohlc[3]) if len(ohlc) > 3 else None
            if last_price is None:
                last_price = _parse_json_number(node.get("sp"))
            ticker = LiveTicker(
                symbol=symbol,
                last_price=last_price,
                mark_price=_parse_json_number(first.get("m")),
                bid=_parse_json_number(quotes[2]) if len(quotes) > 2 else None,
                ask=_parse_json_number(quotes[0]) if len(quotes) > 0 else None,
                change_24h=_parse_json_number(first.get("m24hc")),
                updated_at=datetime.now(timezone.utc),
                price_digits=self.latest_tickers.get(symbol).price_digits
                if symbol in self.latest_tickers
                else None,
            )
            await self._publish(ticker)
        except Exception as exc:
            self.status = "Parsing Error"
            log.debug("Delta message parse failed: %s", exc)

    async def _process_mark_price(self, node: dict) -> None:
        raw_symbol = str(node.get("sy", "")).strip().upper()
        if raw_symbol.startswith("MARK:"):
            symbol = raw_symbol[5:]
        else:
            symbol = raw_symbol
        if not symbol:
            return
        mark_price = _parse_json_number(node.get("p"))
        if mark_price is None:
            return
        existing = self.latest_tickers.get(symbol)
        await self._publish(
            LiveTicker(
                symbol=symbol,
                last_price=existing.last_price if existing else None,
                mark_price=mark_price,
                bid=existing.bid if existing else None,
                ask=existing.ask if existing else None,
                change_24h=existing.change_24h if existing else None,
                updated_at=datetime.now(timezone.utc),
                price_digits=existing.price_digits if existing else None,
            )
        )

    async def _process_ob_l1(self, node: dict) -> None:
        symbol = str(node.get("sy", "")).upper()
        if not symbol:
            return
        bid = _parse_json_number(node.get("bp"))
        ask = _parse_json_number(node.get("ap"))
        if bid is None and ask is None:
            return
        existing = self.latest_tickers.get(symbol)
        await self._publish(
            LiveTicker(
                symbol=symbol,
                last_price=existing.last_price if existing else None,
                mark_price=existing.mark_price if existing else None,
                bid=bid if bid is not None else (existing.bid if existing else None),
                ask=ask if ask is not None else (existing.ask if existing else None),
                change_24h=existing.change_24h if existing else None,
                updated_at=datetime.now(timezone.utc),
                price_digits=existing.price_digits if existing else None,
            )
        )

    def _store_ticker(self, ticker: LiveTicker) -> LiveTicker:
        existing = self.latest_tickers.get(ticker.symbol)
        if ticker.price_digits is None and existing and existing.price_digits is not None:
            ticker = LiveTicker(
                symbol=ticker.symbol,
                last_price=ticker.last_price,
                mark_price=ticker.mark_price,
                bid=ticker.bid,
                ask=ticker.ask,
                change_24h=ticker.change_24h,
                updated_at=ticker.updated_at,
                price_digits=existing.price_digits,
            )
        self.latest_tickers[ticker.symbol] = ticker
        self.last_market_event_at = ticker.updated_at
        self.status = "Subscribed"
        return ticker

    async def _publish(self, ticker: LiveTicker) -> None:
        ticker = self._store_ticker(ticker)
        await self.price_broadcaster.publish(ticker)

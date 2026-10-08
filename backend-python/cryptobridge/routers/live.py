from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from cryptobridge.dependencies import get_market_service, get_private_stream_service, get_snapshot_service, get_user
from cryptobridge.delta.market_data import DeltaMarketDataService, LiveTicker
from cryptobridge.services.snapshot_service import SnapshotService
from cryptobridge.utils.json_safe import json_safe

router = APIRouter(tags=["live"])
log = logging.getLogger(__name__)

SESSION_MESSAGES_PER_LOOP = 4


def _tick_has_price(tick: dict[str, Any]) -> bool:
    for key in ("price", "mark_price", "bid", "ask"):
        value = tick.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return True
    return False


def _build_price_message(ticker: LiveTicker, snapshot: SnapshotService) -> dict[str, Any] | None:
    payload = snapshot.price_update_from(ticker)
    tick = payload.get("tick") or {}
    if not _tick_has_price(tick):
        return None
    payload["topic"] = "price"
    return payload


def _enqueue(queue: asyncio.Queue[dict[str, Any]], payload: dict[str, Any]) -> None:
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(payload)


@router.get("/api/live/prices")
async def live_prices(
    user=Depends(get_user),
    market: DeltaMarketDataService = Depends(get_market_service),
    snapshot: SnapshotService = Depends(get_snapshot_service),
):
    prices: dict[str, Any] = {}
    for symbol, ticker in market.latest_tickers.items():
        update = snapshot.price_update_from(ticker)
        tick = update.get("tick") or {}
        if _tick_has_price(tick):
            prices[symbol] = tick
    return {
        "prices": prices,
        "market_status": market.status,
        "socket_connected": market.socket_connected,
        "subscribed_symbols": market.subscribed_symbols(),
        "last_market_event_at": market.last_market_event_at.isoformat()
        if market.last_market_event_at
        else None,
    }


@router.websocket("/ws/live")
async def live_socket(websocket: WebSocket, token: str = Query("")):
    await websocket.accept()
    state = websocket.app.state
    auth = state.auth_service
    snapshot = state.snapshot_service
    market = state.market_service
    private_stream = state.private_stream_service
    positions_service = state.positions_service
    execution_engine = getattr(state, "execution_engine", None)
    st_options_service = getattr(state, "st_options_service", None)

    price_queue = None
    margin_queue = None
    positions_queue = None
    execution_queue = None
    st_options_queue = None
    forecast_queue = None
    user_id = ""
    worker_tasks: list[asyncio.Task] = []
    connected = True
    price_outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2048)
    session_outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)

    try:
        user = await auth.require_user(token)
        user_id = user["id"]
        initial = await snapshot.snapshot_for(user)

        async def send_payload(payload: dict[str, Any]) -> None:
            nonlocal connected
            if not connected:
                return
            try:
                await websocket.send_json(json_safe(payload))
            except WebSocketDisconnect:
                connected = False
            except Exception as exc:
                connected = False
                # Concurrent close/drain can raise AssertionError from websockets.
                if isinstance(exc, AssertionError) or "disconnect" in str(exc).lower():
                    return
                raise

        await send_payload(initial)
        price_queue = market.price_broadcaster.subscribe()
        try:
            await private_stream.attach_live_client(user)
        except Exception:
            log.exception("Private account stream skipped for user %s", user_id)
        try:
            await positions_service.attach_live_client(user)
        except Exception:
            log.exception("Position stream skipped for user %s", user_id)

        margin_queue = private_stream.broadcaster.subscribe(user_id)
        positions_queue = positions_service.broadcaster.subscribe(user_id)
        try:
            initial_positions = await positions_service.build_open_payload(user)
            await send_payload(initial_positions)
        except Exception:
            pass
        if execution_engine is not None:
            execution_queue = execution_engine.broadcaster.subscribe(user_id)
            try:
                initial_monitors = await execution_engine.list_monitors(user)
                await send_payload(
                    {
                        "type": "execution_monitor",
                        "topic": "execution",
                        "monitors": initial_monitors,
                    }
                )
            except Exception:
                pass
        if st_options_service is not None:
            st_options_queue = st_options_service.broadcaster.subscribe(user_id)
            try:
                await send_payload(await st_options_service.live_snapshot(user))
            except Exception:
                pass
        ai_predictions = getattr(state, "ai_predictions", None)
        if ai_predictions is not None:
            forecast_queue = ai_predictions.broadcaster.subscribe()

        send_lock = asyncio.Lock()

        async def ws_send(payload: dict[str, Any]) -> None:
            nonlocal connected
            if not connected:
                return
            async with send_lock:
                if not connected:
                    return
                try:
                    await send_payload(payload)
                except WebSocketDisconnect:
                    connected = False
                except Exception as exc:
                    connected = False
                    if isinstance(exc, AssertionError) or "disconnect" in str(exc).lower():
                        return
                    raise

        def enqueue_price(ticker: LiveTicker) -> None:
            cached = market.latest_tickers.get(ticker.symbol) or ticker
            message = _build_price_message(cached, snapshot)
            if message is not None:
                _enqueue(price_outbox, message)

        for ticker in list(market.latest_tickers.values()):
            enqueue_price(ticker)

        async def price_queue_reader() -> None:
            while connected:
                ticker = await price_queue.get()
                if not connected:
                    return
                enqueue_price(ticker)

        async def writer_loop() -> None:
            nonlocal connected
            while connected:
                sent_price = False
                while connected:
                    try:
                        payload = price_outbox.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    await ws_send(payload)
                    if not connected:
                        return
                    sent_price = True

                if not connected:
                    return

                for _ in range(SESSION_MESSAGES_PER_LOOP):
                    if not connected:
                        return
                    try:
                        payload = session_outbox.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    await ws_send(payload)
                    if not connected:
                        return

                if sent_price:
                    await asyncio.sleep(0)
                    continue

                get_price = asyncio.create_task(price_outbox.get())
                get_session = asyncio.create_task(session_outbox.get())
                done, pending = await asyncio.wait(
                    {get_price, get_session},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

                if not connected:
                    return

                if get_price in done:
                    await ws_send(get_price.result())
                elif get_session in done:
                    await ws_send(get_session.result())

        async def forward_session_queue(queue: asyncio.Queue[dict[str, Any]]) -> None:
            while connected:
                payload = await queue.get()
                if not connected:
                    return
                topic = "margin" if payload.get("type") == "margin" else "session"
                _enqueue(session_outbox, {**payload, "topic": topic})

        async def forward_positions_queue(queue: asyncio.Queue[dict[str, Any]]) -> None:
            while connected:
                payload = await queue.get()
                if not connected:
                    return
                _enqueue(session_outbox, {**payload, "topic": "positions"})

        async def forward_execution_queue(queue: asyncio.Queue[dict[str, Any]]) -> None:
            while connected:
                payload = await queue.get()
                if not connected:
                    return
                _enqueue(session_outbox, {**payload, "topic": "execution"})

        async def forward_st_options_queue(queue: asyncio.Queue[dict[str, Any]]) -> None:
            while connected:
                payload = await queue.get()
                if not connected:
                    return
                _enqueue(session_outbox, {**payload, "topic": "st_options"})

        async def forward_forecast_queue(queue: asyncio.Queue[dict[str, Any]]) -> None:
            while connected:
                payload = await queue.get()
                if not connected:
                    return
                _enqueue(session_outbox, payload)

        async def receive_client() -> None:
            nonlocal connected
            while connected:
                try:
                    message = await websocket.receive_json()
                except WebSocketDisconnect:
                    connected = False
                    return
                msg_type = str(message.get("type") or "").lower()
                if msg_type == "ping":
                    await ws_send({"topic": "system", "type": "pong"})

        worker_tasks = [
            asyncio.create_task(writer_loop(), name="live-writer"),
            asyncio.create_task(price_queue_reader(), name="live-price-reader"),
            asyncio.create_task(forward_session_queue(margin_queue), name="live-margin"),
            asyncio.create_task(forward_positions_queue(positions_queue), name="live-positions"),
            asyncio.create_task(receive_client(), name="live-receive"),
        ]
        if execution_queue is not None:
            worker_tasks.append(
                asyncio.create_task(forward_execution_queue(execution_queue), name="live-execution")
            )
        if st_options_queue is not None:
            worker_tasks.append(
                asyncio.create_task(forward_st_options_queue(st_options_queue), name="live-st-options")
            )
        if forecast_queue is not None:
            worker_tasks.append(
                asyncio.create_task(forward_forecast_queue(forecast_queue), name="live-forecast")
            )

        await asyncio.gather(*worker_tasks, return_exceptions=True)
    except WebSocketDisconnect:
        connected = False
    except AssertionError:
        # websockets drain race during concurrent close; treat as disconnect.
        connected = False
        log.debug("Live websocket closed with drain race for user %s", user_id or "unknown")
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code == 401:
            log.info("Live websocket auth failed for user %s", user_id or "unknown")
        else:
            log.exception("Live websocket failed for user %s", user_id or "unknown")
        connected = False
        with contextlib.suppress(Exception):
            await websocket.close(code=1008 if status_code == 401 else 1011)
    finally:
        connected = False
        if worker_tasks:
            for task in worker_tasks:
                task.cancel()
            results = await asyncio.gather(*worker_tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException) and not isinstance(
                    result, (asyncio.CancelledError, WebSocketDisconnect, AssertionError)
                ):
                    log.debug("Live websocket worker ended with %s", type(result).__name__)
        if price_queue is not None:
            market.price_broadcaster.unsubscribe(price_queue)
        if margin_queue is not None and user_id:
            private_stream.broadcaster.unsubscribe(user_id, margin_queue)
        if positions_queue is not None:
            positions_service.broadcaster.unsubscribe(user_id, positions_queue)
            await positions_service.detach_live_client(user_id)
        if execution_queue is not None and execution_engine is not None:
            execution_engine.broadcaster.unsubscribe(user_id, execution_queue)
        if st_options_queue is not None and st_options_service is not None:
            st_options_service.broadcaster.unsubscribe(user_id, st_options_queue)
        if forecast_queue is not None:
            ai_predictions = getattr(state, "ai_predictions", None)
            if ai_predictions is not None:
                ai_predictions.broadcaster.unsubscribe(forecast_queue)
        if user_id:
            await private_stream.detach_live_client(user_id)

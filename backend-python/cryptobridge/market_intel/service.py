from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any, Callable

from fastapi import HTTPException

from cryptobridge.exceptions import http_error
from cryptobridge.market_intel.candles import fetch_candles
from cryptobridge.market_intel.schema import DISCLAIMER, AiForecast

log = logging.getLogger(__name__)

MODEL = "gemini-3.8-flash"
CACHE_SECONDS = 15 * 60
GEMINI_ATTEMPTS = 3
GEMINI_RETRY_DELAYS = (2, 4)


class ForecastBroadcaster:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(queue)

    def publish(self, payload: dict[str, Any]) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(payload)


class AiPredictionService:
    def __init__(
        self,
        api_key: str,
        *,
        fetch: Callable[[str], tuple[str, list[dict[str, Any]]]] | None = None,
        generate: Callable[[str], AiForecast] | None = None,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        self._fetch = fetch or fetch_candles
        self._generate = generate or self._generate_with_gemini
        self.broadcaster = ForecastBroadcaster()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._queued: set[str] = set()
        self._jobs: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    async def predict(self, symbol: str) -> dict[str, Any]:
        if not self._api_key:
            raise http_error(503, "GEMINI_API_KEY is not configured.")
        key = str(symbol or "").upper().strip()
        if not key:
            raise http_error(400, "Symbol is required.")
        async with self._lock:
            cached = self._fresh(key)
            if cached is not None:
                return cached
            if key not in self._queued:
                self._queued.add(key)
                self._jobs.put_nowait(key)
            self._ensure_worker()
        return {"status": "pending", "symbol": key}

    def _ensure_worker(self) -> None:
        if self._worker is not None and not self._worker.done():
            return
        self._worker = asyncio.create_task(self._run(), name="ai-predictions")

    async def _run(self) -> None:
        while True:
            symbol = await self._jobs.get()
            try:
                payload = await self._build(symbol)
                self.broadcaster.publish({"type": "ai-prediction", "status": "ready", **payload})
            except Exception as exc:  # noqa: BLE001
                self.broadcaster.publish(
                    {
                        "type": "ai-prediction",
                        "status": "error",
                        "symbol": symbol,
                        "error": _error_text(exc),
                    }
                )
            finally:
                async with self._lock:
                    self._queued.discard(symbol)
                self._jobs.task_done()

    async def _build(self, symbol: str) -> dict[str, Any]:
        venue, candles = await asyncio.to_thread(self._fetch, symbol)
        forecast = await asyncio.to_thread(self._generate, _prompt(symbol, venue, candles))
        if not isinstance(forecast, AiForecast):
            forecast = AiForecast.model_validate(forecast)
        payload = forecast.model_dump()
        payload["disclaimer"] = DISCLAIMER
        payload["symbol"] = symbol
        payload["venue"] = venue
        async with self._lock:
            self._cache[symbol] = (time.monotonic(), payload)
        return payload

    def _fresh(self, symbol: str) -> dict[str, Any] | None:
        cached = self._cache.get(symbol)
        if cached is None:
            return None
        saved_at, payload = cached
        if time.monotonic() - saved_at > CACHE_SECONDS:
            self._cache.pop(symbol, None)
            return None
        return payload

    def _generate_with_gemini(self, prompt: str) -> AiForecast:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key)
        response = None
        for attempt in range(GEMINI_ATTEMPTS):
            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=AiForecast,
                    ),
                )
                break
            except Exception as exc:  # noqa: BLE001
                if attempt < GEMINI_ATTEMPTS - 1 and _is_gemini_unavailable(exc):
                    delay = GEMINI_RETRY_DELAYS[attempt]
                    log.warning("Gemini forecast busy, retrying in %ss: %s: %s", delay, type(exc).__name__, exc)
                    time.sleep(delay)
                    continue
                log.error("Gemini forecast request failed: %s: %s", type(exc).__name__, exc)
                raise http_error(502, "The forecast model did not respond.") from exc
        _log_gemini_response(response)
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, AiForecast):
            return parsed
        if isinstance(parsed, dict):
            return AiForecast.model_validate(parsed)
        text = getattr(response, "text", None) or ""
        if not text:
            raise http_error(502, "The forecast model did not respond.")
        return AiForecast.model_validate_json(text)


def _is_gemini_unavailable(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 503:
        return True
    text = str(exc).upper()
    return "503" in text and "UNAVAILABLE" in text


def _error_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return str(detail.get("detail") or detail.get("error") or "Forecast unavailable.")
        if detail:
            return str(detail)
    return "Forecast unavailable."


def _log_gemini_response(response: Any) -> None:
    candidates = getattr(response, "candidates", None) or []
    finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    log.info(
        "Gemini forecast response text=%r parsed=%r finish_reason=%r",
        getattr(response, "text", None),
        getattr(response, "parsed", None),
        finish_reason,
    )
    prompt_feedback = getattr(response, "prompt_feedback", None)
    if prompt_feedback is not None:
        log.info("Gemini forecast prompt_feedback=%r", prompt_feedback)


def _prompt(symbol: str, venue: str, candles: list[dict[str, Any]]) -> str:
    lines = [
        f"{int(row['time'])} o={row['open']} h={row['high']} l={row['low']} c={row['close']} v={row['volume']}"
        for row in candles[-48:]
    ]
    return (
        "You are a market technician. Using only these recent 1-hour candles, "
        "estimate the chance the next move is up (bullish) or down (bearish) "
        f"for {symbol} ({venue}). Percentages are integers from 0 to 100. "
        "Keep the rationale to a few sentences about the candle structure.\n"
        + "\n".join(lines)
    )

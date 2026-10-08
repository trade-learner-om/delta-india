from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from cryptobridge.exceptions import http_error
from cryptobridge.market_intel.candles import fetch_candles
from cryptobridge.market_intel.schema import DISCLAIMER, AiForecast

log = logging.getLogger(__name__)

MODEL = "gemini-3.8-flash"
CACHE_SECONDS = 15 * 60


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
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._inflight: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

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
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._build(key))
                self._inflight[key] = task
        try:
            return await task
        finally:
            async with self._lock:
                current = self._inflight.get(key)
                if current is task:
                    self._inflight.pop(key, None)

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
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AiForecast,
                ),
            )
        except Exception as exc:  # noqa: BLE001
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

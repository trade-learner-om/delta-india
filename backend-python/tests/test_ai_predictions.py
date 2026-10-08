import asyncio
import logging
import threading

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from cryptobridge.market_intel.candles import CRYPTO_PAIRS, FOREX_TICKERS, venue_for
from cryptobridge.market_intel.schema import DISCLAIMER, AiForecast, Horizon
from cryptobridge.market_intel.service import MODEL, AiPredictionService


def _forecast() -> AiForecast:
    horizon = Horizon(bullish=60, bearish=40)
    return AiForecast(
        horizon_1h=horizon,
        horizon_4h=horizon,
        horizon_24h=horizon,
        technical_rationale="Higher lows on the last candles.",
        disclaimer="model text",
    )


def test_symbol_maps_cover_the_universe():
    assert CRYPTO_PAIRS == {"BTCUSD": "BTC/USDT", "ETHUSD": "ETH/USDT", "SOLUSD": "SOL/USDT"}
    assert set(FOREX_TICKERS) == {
        "EURUSD",
        "GBPUSD",
        "AUDUSD",
        "NZDUSD",
        "USDCAD",
        "USDCHF",
        "USDJPY",
        "EURJPY",
        "GBPJPY",
        "XAUUSD",
        "XAGUSD",
    }
    assert FOREX_TICKERS["XAUUSD"] == "GC=F"
    assert FOREX_TICKERS["XAGUSD"] == "SI=F"
    assert venue_for("btcusd") == "crypto"
    assert venue_for("XAUUSD") == "forex"
    assert MODEL == "gemini-3.8-flash"


def test_unknown_symbol_is_rejected():
    with pytest.raises(HTTPException) as exc:
        venue_for("DOGEUSD")
    assert exc.value.status_code == 400


def test_horizon_percentages_stay_in_range():
    with pytest.raises(ValidationError):
        Horizon(bullish=101, bearish=0)


@pytest.mark.asyncio
async def test_predict_returns_pending_then_pushes_and_caches():
    calls = {"n": 0}

    def fetch(symbol):
        return "crypto", [{"time": 1, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 3}]

    def generate(prompt):
        calls["n"] += 1
        assert "BTCUSD" in prompt
        return _forecast()

    service = AiPredictionService("test-key", fetch=fetch, generate=generate)
    updates = service.broadcaster.subscribe()
    try:
        pending = await service.predict("btcusd")
        assert pending == {"status": "pending", "symbol": "BTCUSD"}
        ready = await asyncio.wait_for(updates.get(), timeout=2)
        assert ready["status"] == "ready"
        assert ready["type"] == "ai-prediction"
        assert ready["disclaimer"] == DISCLAIMER
        assert ready["venue"] == "crypto"
        cached = await service.predict("BTCUSD")
        assert cached["disclaimer"] == DISCLAIMER
        assert calls["n"] == 1
    finally:
        service.broadcaster.unsubscribe(updates)
        await service.aclose()


@pytest.mark.asyncio
async def test_forecast_jobs_run_one_at_a_time():
    started = threading.Event()
    release = threading.Event()

    def fetch(symbol):
        return "crypto", [{"time": 1, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 3}]

    def generate(prompt):
        started.set()
        assert release.wait(timeout=2)
        return _forecast()

    service = AiPredictionService("test-key", fetch=fetch, generate=generate)
    updates = service.broadcaster.subscribe()
    try:
        await service.predict("BTCUSD")
        await service.predict("ETHUSD")
        for _ in range(40):
            if started.is_set():
                break
            await asyncio.sleep(0.05)
        assert started.is_set()
        await asyncio.sleep(0.05)
        assert updates.empty()
        release.set()
        first = await asyncio.wait_for(updates.get(), timeout=2)
        second = await asyncio.wait_for(updates.get(), timeout=2)
        assert {first["symbol"], second["symbol"]} == {"BTCUSD", "ETHUSD"}
        assert first["status"] == "ready"
        assert second["status"] == "ready"
    finally:
        release.set()
        service.broadcaster.unsubscribe(updates)
        await service.aclose()


@pytest.mark.asyncio
async def test_missing_api_key_is_unavailable():
    service = AiPredictionService("")
    with pytest.raises(HTTPException) as exc:
        await service.predict("BTCUSD")
    assert exc.value.status_code == 503


class _Candidate:
    def __init__(self, finish_reason):
        self.finish_reason = finish_reason


class _GeminiResponse:
    def __init__(self, text, parsed, finish_reason, prompt_feedback=None):
        self.text = text
        self.parsed = parsed
        self.candidates = [_Candidate(finish_reason)]
        self.prompt_feedback = prompt_feedback


class _GeminiClient:
    last_model = None

    def __init__(self, api_key):
        self.api_key = api_key
        self.models = self

    def generate_content(self, **kwargs):
        _GeminiClient.last_model = kwargs.get("model")
        return _GeminiResponse(
            text='{"marker":"candle-structure"}',
            parsed=_forecast(),
            finish_reason="STOP",
            prompt_feedback="allowed",
        )


class _FailingGeminiClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.models = self

    def generate_content(self, **kwargs):
        raise RuntimeError("quota exceeded")


def test_gemini_response_text_is_logged(monkeypatch, caplog):
    monkeypatch.setattr("google.genai.Client", _GeminiClient)
    service = AiPredictionService("secret-gemini-key")
    with caplog.at_level(logging.INFO, logger="cryptobridge.market_intel.service"):
        forecast = service._generate_with_gemini("prompt")
    assert forecast.technical_rationale == "Higher lows on the last candles."
    assert _GeminiClient.last_model == "gemini-3.8-flash"
    assert '{"marker":"candle-structure"}' in caplog.text
    assert "STOP" in caplog.text
    assert "allowed" in caplog.text
    assert "secret-gemini-key" not in caplog.text


class _BusyGeminiClient:
    calls = 0

    def __init__(self, api_key):
        self.api_key = api_key
        self.models = self

    def generate_content(self, **kwargs):
        type(self).calls += 1
        if type(self).calls == 1:
            raise RuntimeError("503 UNAVAILABLE")
        return _GeminiResponse(
            text='{"marker":"candle-structure"}',
            parsed=_forecast(),
            finish_reason="STOP",
        )


class _AlwaysBusyGeminiClient:
    calls = 0

    def __init__(self, api_key):
        self.api_key = api_key
        self.models = self

    def generate_content(self, **kwargs):
        type(self).calls += 1
        raise RuntimeError("503 UNAVAILABLE")


def test_gemini_retries_a_busy_response(monkeypatch, caplog):
    delays = []
    monkeypatch.setattr("google.genai.Client", _BusyGeminiClient)
    monkeypatch.setattr("cryptobridge.market_intel.service.time.sleep", delays.append)
    _BusyGeminiClient.calls = 0
    service = AiPredictionService("secret-gemini-key")
    with caplog.at_level(logging.WARNING, logger="cryptobridge.market_intel.service"):
        forecast = service._generate_with_gemini("prompt")
    assert forecast.technical_rationale == "Higher lows on the last candles."
    assert _BusyGeminiClient.calls == 2
    assert delays == [2]
    assert "retrying in 2s" in caplog.text


def test_gemini_busy_response_fails_after_three_tries(monkeypatch, caplog):
    delays = []
    monkeypatch.setattr("google.genai.Client", _AlwaysBusyGeminiClient)
    monkeypatch.setattr("cryptobridge.market_intel.service.time.sleep", delays.append)
    _AlwaysBusyGeminiClient.calls = 0
    service = AiPredictionService("secret-gemini-key")
    with caplog.at_level(logging.WARNING, logger="cryptobridge.market_intel.service"):
        with pytest.raises(HTTPException) as exc:
            service._generate_with_gemini("prompt")
    assert exc.value.status_code == 502
    assert _AlwaysBusyGeminiClient.calls == 3
    assert delays == [2, 4]
    assert "retrying in 4s" in caplog.text


def test_gemini_sdk_error_is_logged(monkeypatch, caplog):
    monkeypatch.setattr("google.genai.Client", _FailingGeminiClient)
    service = AiPredictionService("secret-gemini-key")
    with caplog.at_level(logging.ERROR, logger="cryptobridge.market_intel.service"):
        with pytest.raises(HTTPException) as exc:
            service._generate_with_gemini("prompt")
    assert exc.value.status_code == 502
    assert "RuntimeError" in caplog.text
    assert "quota exceeded" in caplog.text
    assert "secret-gemini-key" not in caplog.text

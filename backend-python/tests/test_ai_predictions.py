import logging

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from cryptobridge.market_intel.candles import CRYPTO_PAIRS, FOREX_TICKERS, venue_for
from cryptobridge.market_intel.schema import DISCLAIMER, AiForecast, Horizon
from cryptobridge.market_intel.service import AiPredictionService


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
    assert venue_for("btcusd") == "crypto"
    assert venue_for("XAUUSD") == "forex"


def test_unknown_symbol_is_rejected():
    with pytest.raises(HTTPException) as exc:
        venue_for("DOGEUSD")
    assert exc.value.status_code == 400


def test_horizon_percentages_stay_in_range():
    with pytest.raises(ValidationError):
        Horizon(bullish=101, bearish=0)


@pytest.mark.asyncio
async def test_predict_uses_the_fixed_disclaimer_and_cache():
    calls = {"n": 0}

    def fetch(symbol):
        return "crypto", [{"time": 1, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 3}]

    def generate(prompt):
        calls["n"] += 1
        assert "BTCUSD" in prompt
        return _forecast()

    service = AiPredictionService("test-key", fetch=fetch, generate=generate)
    first = await service.predict("btcusd")
    second = await service.predict("BTCUSD")
    assert first["disclaimer"] == DISCLAIMER
    assert first["venue"] == "crypto"
    assert second is first or second["technical_rationale"] == first["technical_rationale"]
    assert calls["n"] == 1


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
    def __init__(self, api_key):
        self.api_key = api_key
        self.models = self

    def generate_content(self, **kwargs):
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
    assert '{"marker":"candle-structure"}' in caplog.text
    assert "STOP" in caplog.text
    assert "allowed" in caplog.text
    assert "secret-gemini-key" not in caplog.text


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

from __future__ import annotations

from typing import Any

from cryptobridge.exceptions import http_error

CANDLE_LIMIT = 48

CRYPTO_PAIRS = {
    "BTCUSD": "BTC/USDT",
    "ETHUSD": "ETH/USDT",
    "SOLUSD": "SOL/USDT",
}

FOREX_TICKERS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "USDJPY": "USDJPY=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
}


def venue_for(symbol: str) -> str:
    key = str(symbol or "").upper().strip()
    if key in CRYPTO_PAIRS:
        return "crypto"
    if key in FOREX_TICKERS:
        return "forex"
    raise http_error(400, "Symbol is not in the forecast universe.")


def fetch_candles(symbol: str) -> tuple[str, list[dict[str, Any]]]:
    key = str(symbol or "").upper().strip()
    venue = venue_for(key)
    rows = _fetch_crypto(key) if venue == "crypto" else _fetch_forex(key)
    if not rows:
        raise http_error(400, "No recent candles for that symbol.")
    return venue, rows


def _fetch_crypto(symbol: str) -> list[dict[str, Any]]:
    import ccxt

    exchange = ccxt.binance({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(CRYPTO_PAIRS[symbol], timeframe="1h", limit=CANDLE_LIMIT) or []
    return [
        {
            "time": int(row[0] / 1000),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5] or 0),
        }
        for row in raw[-CANDLE_LIMIT:]
        if row and len(row) >= 6
    ]


def _fetch_forex(symbol: str) -> list[dict[str, Any]]:
    import yfinance as yf

    frame = yf.download(
        FOREX_TICKERS[symbol],
        period="5d",
        interval="1h",
        progress=False,
        auto_adjust=False,
    )
    return _frame_rows(frame)


def _frame_rows(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    columns = frame.columns
    if hasattr(columns, "nlevels") and columns.nlevels > 1:
        frame = frame.copy()
        frame.columns = columns.get_level_values(0)
    rows: list[dict[str, Any]] = []
    for ts, row in frame.tail(CANDLE_LIMIT).iterrows():
        try:
            rows.append(
                {
                    "time": int(ts.timestamp()),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"] or 0) if "Volume" in row else 0.0,
                }
            )
        except (TypeError, ValueError, KeyError):
            continue
    return rows

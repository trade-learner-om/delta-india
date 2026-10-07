# Candle Store

Persistent M1 candles built from live ticks and hydrated from Delta history.

## Components

| Module | Role |
|--------|------|
| `utils/candle_builder.py` | Aggregate ticks into 1m OHLC bars |
| `services/candle_store_service.py` | Mongo `candle_bars` CRUD + gap hydration |
| `services/candle_ingest_service.py` | Subscribe to market ticks → builder → store |

## MongoDB `candle_bars`

Unique index: `(symbol, resolution, time)`

Fields: `open`, `high`, `low`, `close`, `volume`, `complete`, `source` (`tick` | `delta`), `updatedAt`

## Hydration

`ensure_range(symbol, "1m", start, end)` loads local bars, detects missing minutes, fetches gaps from `GET /v2/history/candles`, upserts, returns merged series.

Used by RWB backtest and candle detector preview.

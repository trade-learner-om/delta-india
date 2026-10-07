# BTC MV Straddle Buy

Long **MV straddle** backtest on Delta India BTC/ETH MOVE products (`MV-*`). Route remains `/move-straddle`; UI label **BTC MV Straddle Buy**.

## Session rules

| Rule | Value |
|------|--------|
| Instrument | Long daily **MOVE** straddle (MV mark candles) |
| MV product | Expiry = **next calendar day** when `startTime >= 17:30`, else **same day**; nearest ATM strike at that expiry |
| Session start | User **startTime** (default **18:30 IST**) — anchor time; 5 EMA seeds from first mark bar in setup window |
| Setup window | **startTime** – **stopTime** (default **22:30 IST**); if stop clock ≤ start, stop is next day |
| Anchor bar | First `MARK:MV-*` 5m candle with open time in `[startTime, stopTime)`; may be later than exact anchor |
| Timeframe | **5m** `MARK:MV-*` OHLC |
| Entry | Shooting star with close **below** 5 EMA → buy stop at star high + 1, SL at star low − 1 |
| Sizing | `riskAmount / (entry − SL)` via `compute_position_size` |
| T1 | 50% @ **6R**; move SL to breakeven on remainder |
| T2 | Remaining 50% @ **20R** |
| Daily halt | After **2** full stop-outs (no T1/T2), no new setups rest of IST day |
| Post-window | Filled positions keep managing T1/T2/SL after stopTime until MV settlement |

## Backtest API

`POST /api/move-straddle/backtest`

```json
{
  "startDate": "2026-06-23",
  "endDate": "2026-06-30",
  "underlying": "BTC",
  "riskAmount": 100,
  "startTime": "18:30",
  "stopTime": "22:30"
}
```

Defaults: `startDate` = today − 7 days, `endDate` = today (UI + server).

**Result** (`backtestJob.result` when completed):

| Field | Description |
|-------|-------------|
| `stats` | Calendar-style extended stats (`totalPnl`, win rate, drawdown, …) |
| `trades[]` | Per attempt: entry, sl, ema, targets, hitT1/hitT2, result, totalPnl |
| `equityCurve` | Cumulative PnL points |
| `exclusionReasons` | Counts per skip reason (`no_mv_product`, `no_setup`, `daily_halt`, …) |
| `sessionDiagnostics[]` | Per-day: bars, in-window scans, shooting stars, pending placed/filled, skip reason, `targetExpiry`, `productExpiry`, `expiryFallback`, events |
| `diagnosticSummary` | Aggregated signal/pending/anchor-misalignment counts |

WebSocket: `type: move_straddle`, `topic: move_straddle` — includes `backtestJob`.

## Live

`POST /api/move-straddle/live/start` returns **501** until live engine ships.

## Code map

| Layer | Path |
|-------|------|
| Helpers | `backend-python/cryptobridge/utils/move_straddle_helpers.py` |
| Indicators | `backend-python/cryptobridge/utils/indicators.py` |
| Patterns | `backend-python/cryptobridge/utils/candlestick_patterns.py` |
| Backtest engine | `backend-python/cryptobridge/utils/move_straddle_backtest.py` |
| Service | `backend-python/cryptobridge/services/move_straddle_service.py` |
| Router | `backend-python/cryptobridge/routers/move_straddle.py` |
| UI | `frontend-react/src/components/movestraddle/MoveStraddlePage.jsx` |

# Open Break Writer (OBW)

Backtest-only strategy for Delta Exchange India crypto options. Live execution is planned for a later phase.

## Strategy name

**Open Break Writer** — code id: `open_break_writer`

## Rules

1. **Underlying:** Any crypto futures asset (e.g. `BTC`, `ETH`).
2. **Session start (default 18:30 IST):** Mark the underlying **open** from the first 1m candle at/after start time.
3. **Upside break:** When underlying moves up by the configured **trigger** (% or points) from session open → **sell CALL** at the selected strike offset.
4. **Downside break:** When underlying moves down by the trigger → **sell PUT** at the selected strike offset.
5. **Strike offset:** User selects `ITM10 … ITM1`, `ATM`, `OTM1 … OTM10` relative to spot at trigger time.
6. **Position limit:** Max one open CALL and one open PUT per session; each direction re-arms after that leg closes.
7. **Stop loss:** Premium rises by configured % or points from entry (short option loss).
8. **Take profit:** One of:
   - **Underlying target** — underlying moves favorably from leg entry spot by amount (same unit as trigger mode)
   - **Premium %** — premium decays by X% from entry
   - **Premium target** — absolute premium level
9. **Session end (default 17:30 IST):** If end time is before start time on the clock, window crosses midnight (e.g. 18:30 → next day 17:30). Open legs force-closed at last bar.
10. **No trade range (optional):** Two IST times; if start is after end on the clock, end is the next day. New CALL/PUT entries are blocked during this window; open legs are still managed.

## Backtest data

- Underlying: `GET /v2/history/candles` on `{UNDERLYING}USD` (1m).
- Options: `GET /v2/products?states=expired` for historical contracts + option symbol candles.
- PnL: `(entry_premium - exit_premium) × lots × contract_value` (no fees/slippage in v1).

## API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/options/backtest/meta` | Strategy id, strike offsets, mode enums |
| POST | `/api/options/backtest/run` | Start async date-range backtest on a dedicated worker thread; returns `{ jobId, status }` immediately |
| GET | `/api/options/backtest/jobs/{jobId}` | Poll job status/result (live socket also pushes completion) |

### Example request

```json
{
  "underlying": "BTC",
  "startDate": "2024-01-15",
  "endDate": "2024-01-31",
  "sessionStartTime": "18:30",
  "sessionEndTime": "17:30",
  "lots": 10,
  "triggerMode": "percent",
  "triggerAmount": 2,
  "strikeOffset": "OTM2",
  "stopLossMode": "percent",
  "stopLossAmount": 50,
  "takeProfitMode": "premium_percent",
  "takeProfitAmount": 50,
  "noTradeStartTime": "22:00",
  "noTradeEndTime": "06:00"
}
```

## UI

**Options** page → **Backtest** tab → configure and run Open Break Writer.

## Code layout

| Module | Role |
|--------|------|
| `utils/strike_ladder.py` | ITM/ATM/OTM strike selection |
| `services/open_break_writer_engine.py` | Pure session simulator |
| `services/historical_option_chain.py` | Expired products + candle fetch |
| `services/options_backtest_service.py` | Date-range orchestration |
| `routers/options_backtest.py` | REST endpoints |

## Assumptions

- 1-minute resolution for underlying and options.
- Entry at option candle close at trigger minute; SL uses bar high, premium TP uses bar low.
- Missing historical option candles → trade skipped (logged in day events).

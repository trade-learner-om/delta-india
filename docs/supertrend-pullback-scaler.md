# SuperTrend Pullback Scaler (SPS)

**Product:** Short-vol options on BTC / ETH  
**UI route:** `sps` nav (**ST Pullback**)  
**Timeframe:** 90m IST-aligned bars (aggregated from 15m)  
**Code:** `utils/sps_indicators.py`, `utils/sps_option_resolver.py`, `services/sps_engine.py`, `services/sps_service.py`, `services/sps_backtest_service.py`

---

## Indicators (TradingView parity)

| Indicator | Parameters | Base |
|-----------|------------|------|
| EMA | 20 | Close — SMA seed over first 20 bars |
| SuperTrend | 8, 3 | **HL2** — RMA ATR (`ta.atr`), Pine `ta.supertrend` default; ternary band pinning vs **prior** bar bands, Pine state-machine direction flip, line on current pinned band |

Indicators are computed on **120 days** of 90m history before the visible window (backtest and live) so EMA/ST match TradingView rather than cold-starting on the selected range.

**SuperTrend algorithm (TV default parity):**
- **Source:** `hl2 = (high + low) / 2` — matches built-in TradingView SuperTrend (Length 8, Factor 3).
- **Pinning:** `upper = basic_upper` if prior close > prior upper, else `min(basic_upper, prior upper)`; symmetric for lower band.
- **Direction:** Pine state machine — if prior line was on upper band, green when close > current upper else red; if prior line was on lower band, red when close < current lower else green.
- **Line:** lower band when green, upper band when red.

- **Green (up):** SuperTrend line on lower band  
- **Red (down):** SuperTrend line on upper band  

Backtest **90m Bar Ledger** shows `hl2`, `stUpper`, `stLower`, `stLine`, `stLineForTap`, `stTapped`, and `tapTimeIst` for Data Window comparison. Last **5** closed bars also log in backtest trace and live indicator refresh.

Drift diagnostics log bot EMA/ST every **100** bars (`driftLog[]` in backtest).

---

## Entry (single leg, full size)

**Arm on ST flip;** scan **1m spot** candles inside each 90m bucket `[bar_open, bar_open + 90m)` until price taps the SuperTrend line. Tap test uses the **prior closed 90m bar’s** ST line (no lookahead into the forming bucket).

| ST color (armed) | Direction | ST line for tap | 1m tap condition |
|------------------|-----------|-----------------|------------------|
| **Green** | Short **PUT** | Prior closed 90m ST | `low <= st_line` |
| **Red** | Short **CALL** | Prior closed 90m ST | `high >= st_line` |

Entry time = **tap minute**; entry spot = 1m close at tap. Option premium from **1m option candles** at or before tap time (backtest); live mark at resolve.

**Concurrency:** At most **one open trade per direction** (put vs call). Opposite ST flip re-arms the watch direction.

### Strike & expiry

- **Anchor:** ST line at tap snapped **ITM-ward** to grid — put: `ceil(ST/20)×20` (ETH) or `ceil(ST/200)×200` (BTC); call: `floor` (never OTM).
- **Waterfall:** up to **3** strikes (anchor, +1 ITM step, +2 ITM steps) on **T+2**; min premium **`spot × 1%`** at tap.
- **Fallback:** if T+2 waterfall fails, repeat on **T+3** (`expiryFallback` on trade row).
- Skip only when all strikes/expiry combinations fail the premium gate.

---

## Trade management (premium-only)

- **No exit on ST color flip** while in trade  
- **Stop loss:** premium **+50%** → exit at **1.5×** entry (`stop_loss_premium`)  
- **Take profit:** premium **−90%** → exit at **0.1×** entry (`take_profit_premium`)  
- Bracket evaluated on **15m option candle high/low** (not close).  
- Live marks from ticker; SL/TP closes record exact bracket prices.

---

## Quantity & PnL

- User **quantity** = coin (1 BTC / 1 ETH) — **full size on entry**  
- **Lots:** 1 BTC = 1000 lots (`contract_value` 0.001); 1 ETH = 100 lots (`0.01`)  
- PnL: `(entry − exit) × contract_value × lots` on full `quantity`

---

## Ledger fields

`leg1Price` / `avgEntryPrice` (entry premium), `expiry`, `strike`, `stLineValue`, `ema20`, `entryTapTime` (live), `contractLots`, `totalPnl`. Legacy `leg2*` fields remain null.

---

## API

| Method | Path |
|--------|------|
| GET | `/api/sps/meta` |
| POST | `/api/sps/start` | `{ symbol, quantity }` |
| POST | `/api/sps/stop` |
| GET | `/api/sps/live` | includes `backtestJob` when running |
| GET | `/api/sps/history` |
| POST | `/api/sps/backtest` | async job `{ id, status: processing }` — returns immediately; progress/trace stream on WS |
| POST | `/api/sps/backtest/run` | alias → async submit |

**WebSocket:** `type: sps_session` — `setups[]`, `active[]`, `backtestJob`, indicator snapshot on last closed 90m bar.

**Backtest:** `bars90m[]` per-bar OHLC + EMA + ST + tap fields; `traceLog`; `diagnostics` (`stTapPass`, etc.).

---

## MongoDB

| Collection | Purpose |
|------------|---------|
| `sps_setups` | Per-user scanner config (`enabled`, `quantity`) |
| `sps_trades` | Live short-option positions |

**Legacy (read-only):** `directional_options_*` collections are no longer written.

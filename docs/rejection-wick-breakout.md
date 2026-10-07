# Rejection Wick Breakout (RWB) — Complete Strategy Reference

**Product:** Wick Break (vanilla RWB on perp futures)  
**UI route:** Wick Break nav (`RwbPage`)  
**Tabs:** Live · History · Backtest  
**Spec version:** 2026-07-12

This document is the **single technical and business-logic source of truth** for the **1m perp futures** Wick Break product. It covers pattern rules, the trade FSM, sizing, fees, live execution, backtest simulation, API, MongoDB, and UI.

> **Not the same product as SPS (ST Pullback).** [SuperTrend Pullback Scaler](./supertrend-pullback-scaler.md) sells short options on **90m** bars using SuperTrend + EMA filters. Wick Break trades **BTCUSD/ETHUSD perp futures** directly on **1m/5m/15m** bars with hammer/shooting-star geometry; an optional **H1 unmitigated swing** proximity gate is available.

**Code roots:** `backend-python/cryptobridge/services/rwb_engine.py`, `rwb_service.py`, `rwb_execution.py`, `rwb_backtest_service.py`, `utils/candle_patterns.py`, `utils/candle_levels.py`, `utils/risk_sizing.py`, `utils/market_structure.py`

**Related:** [FEATURES.md §9](./FEATURES.md) (product inventory) · [CHANGELOG.md](./CHANGELOG.md) (history)

---

## Table of contents

1. [Business purpose](#1-business-purpose)
2. [Glossary](#2-glossary)
3. [Strategy at a glance](#3-strategy-at-a-glance)
4. [Instruments and market conventions](#4-instruments-and-market-conventions)
5. [Candle pattern geometry](#5-candle-pattern-geometry)
6. [Structure validation (C3 / C2 / C1)](#6-structure-validation-c3--c2--c1)
7. [Trade direction mapping](#7-trade-direction-mapping)
8. [Entry, stop, and R definition](#8-entry-stop-and-r-definition)
9. [Pre-entry filters](#9-pre-entry-filters)
10. [Finite-state machine](#10-finite-state-machine)
11. [Entry fill and timeout](#11-entry-fill-and-timeout)
12. [Trade management — partial book and final target](#12-trade-management--partial-book-and-final-target)
13. [Position sizing](#13-position-sizing)
14. [Fees and PnL](#14-fees-and-pnl)
15. [Live engine](#15-live-engine)
16. [Backtest engine](#16-backtest-engine)
17. [Configuration reference](#17-configuration-reference)
18. [REST API](#18-rest-api)
19. [WebSocket](#19-websocket)
20. [MongoDB](#20-mongodb)
21. [Frontend flows](#21-frontend-flows)
22. [Reject and activity reason codes](#22-reject-and-activity-reason-codes)
23. [Live vs backtest parity](#23-live-vs-backtest-parity)
24. [Edge cases and limitations](#24-edge-cases-and-limitations)
25. [Troubleshooting FAQ](#25-troubleshooting-faq)
26. [Source file map](#26-source-file-map)

---

## 1. Business purpose

### 1.1 What the strategy trades

Wick Break is a **directional perp futures** strategy on Delta Exchange India:

- **Hammer** (lower-wick rejection, **short bias**) → **SHORT** (sell perp, breakdown below signal low)
- **Shooting star** (upper-wick rejection, **long bias**) → **LONG** (buy perp, breakout above signal high)

Setups are validated on **closed 1m candles** using wick geometry plus a four-bar structure rule (C3 → C2 → C1 → signal). There are **no** EMA, ATR, volume, or options filters. An optional **H1 unmitigated swing** proximity gate can require the signal wick to sit near a structural H1 level before entry.

### 1.2 Economic intent

| Pattern | Perp side | Idea |
|---------|-----------|------|
| **Shooting star** | BUY (long) | Upper-wick rejection (long bias); enter on break above signal high; stop below signal low |
| **Hammer** | SELL (short) | Lower-wick rejection (short bias); enter on break below signal low; stop above signal high |

Profit comes from reaching **partial book** (default 4R on half size) and **final target** (default 20R on remainder). Loss is capped at the initial stop (before breakeven move).

### 1.3 What “success” means in the product

- **Live:** Scanner watches 1m bars; on valid signal places a **stop-limit style entry** at the breakout level with bracket stop; manages partial exit and breakeven; runs until user stops the session.
- **Backtest:** Replays the same FSM on historical 1m candles; produces summary stats, equity curve, year-wise returns, and a paginated trade ledger.

---

## 2. Glossary

| Term | Meaning |
|------|---------|
| **R** | `|entry − stop_loss|` in **price points** (USD for BTCUSD/ETHUSD) |
| **Signal bar** | The closed 1m candle at index `i` that passes hammer or shooting-star geometry + structure |
| **C3, C2, C1** | The three bars immediately before the signal: `bars[i−3]`, `bars[i−2]`, `bars[i−1]` |
| **Structural extreme** | For hammers, C3 low is the lowest low in the four-bar window; for shooting stars, C3 high is the highest high |
| **Entry** | Stop-entry trigger price (1 tick beyond signal wick) |
| **Stop loss (SL)** | Protective stop (1 tick beyond opposite wick) |
| **Partial book (T1)** | First profit target at `partialBookR` × R; closes `partialBookPct` of position |
| **Final target (T2)** | Remainder target at `20R` by default |
| **Contract** | Delta futures lot; PnL scales by `contract_value` (BTCUSD typically `0.001`) |
| **Max risk** | Dollar amount risked to **initial SL on price move** (gross, before fees) when `sizingMode = max_risk` |
| **Min SL distance** | Minimum `|entry − stop|` in price points; tighter setups are rejected |
| **H1 swing filter** | Optional gate: shooting-star high near unmitigated H1 swing **high** (long); hammer low near swing **low** (short) |
| **Swing level** | Nearest matching H1 unmitigated level when the swing filter passes; stored on trades for ledger analysis |

---

## 3. Strategy at a glance

```
SCANNING
  └─ closed 1m bar completes
       └─ pattern + structure OK?
            └─ |entry − SL| ≥ minSlDistance?
                 └─ (optional) H1 swing proximity OK?
                      └─ PENDING_ENTRY (SL entry order, 5-bar timeout)
                      └─ filled → MANAGE_TRADE
                           ├─ SL hit → flat (loss)
                           ├─ partialBookR hit → book partialBookPct, SL → breakeven
                           └─ 20R hit on remainder → flat (win)
```

**Hard rules:**

- Only **one open position per session symbol** at a time; no new scans while `pending_entry` or `manage_trade`.
- Minimum **5 bars** of history required before any signal (`index ≥ 4`).
- **Fill timeout:** 5 completed 1m bars while pending; then cancel and resume scanning.
- **Final target:** fixed at **20R** in backtest; live sessions store `target2R = 20` unless overridden at start (API).

---

## 4. Instruments and market conventions

| Field | Value |
|-------|-------|
| **Symbols** | `BTCUSD`, `ETHUSD` (perp futures) |
| **Bar resolution** | `1m`, `5m`, or `15m` via `timeframe` config (`CandleCacheService`) |
| **Timezone** | IST for backtest date windows and optional no-trade windows |
| **Tick size** | From `GET /v2/products` (`tick_size` on session doc) |
| **Contract value** | From product metadata (`contract_value`, e.g. `0.001` BTC per contract) |
| **Taker fee** | Product `taker_commission_rate` or default `0.0005` (0.05%) + **18% GST** in simulation |

Live orders use the user’s **selected Delta account** from Account Settings.

---

## 5. Candle pattern geometry

Implemented in `utils/candle_patterns.py`. Constants:

| Constant | Value | Role |
|----------|-------|------|
| `DOMINANT_WICK_RANGE_RATIO` | `0.5` | Dominant wick must exceed **50%** of total candle range |
| `MAX_BODY_RANGE_RATIO` | `0.2` | Body must be **&lt; 20%** of range |
| `OPPOSITE_WICK_RATIO` | `0.3` | Non-dominant wick must be **&lt; 30%** of dominant wick |

### 5.1 Hammer (bullish rejection)

On signal bar:

- `lower_wick > 50%` of `(high − low)`
- `body < 20%` of range
- `upper_wick < 30%` of `lower_wick`

### 5.2 Shooting star (bearish rejection)

Mirrored:

- `upper_wick > 50%` of range
- `body < 20%` of range
- `lower_wick < 30%` of `upper_wick`

### 5.3 Evaluation order

`evaluate_pattern()` checks **shooting star first**, then hammer. At most one pattern per bar.

---

## 6. Structure validation (C3 / C2 / C1)

After geometry matches, structure is validated across **C3, C2, C1, signal** (`RWB_STRUCTURE_BARS = 5`).

### 6.1 Hammer structure

| Rule | Reject reason |
|------|----------------|
| C3 low must be the **lowest** low among all four bars | `C-3 must be the structural low` |
| Signal (hammer) low **>** C3 low | `Hammer low must stay above C-3 low` |
| C2 low **>** C3 low | `C-2 low must stay above C-3 low` |
| C1 low **>** C3 low | `C-1 low must stay above C-3 low` |

### 6.2 Shooting star structure

| Rule | Reject reason |
|------|----------------|
| C3 high must be the **highest** high among all four bars | `C-3 must be the structural high` |
| Signal high **&lt;** C3 high | `Shooting star high must stay below C-3 high` |
| C2 high **&lt;** C3 high | `C-2 high must stay below C-3 high` |
| C1 high **&lt;** C3 high | `C-1 high must stay below C-3 high` |

Live sessions log structure rejects in the activity feed (`event: signal_rejected`, `rejectReason` = messages above).

---

## 7. Trade direction mapping

**Vanilla Wick Break (this product)** — `signal_side()` in `candle_patterns.py`:

| Pattern | Perp `side` | Direction |
|---------|---------------|-----------|
| `shooting_star` | `BUY` | Long |
| `hammer` | `SELL` | Short |

Wick Break and Directional Options share the same **pattern bias**: shooting star = long, hammer = short (`pattern_to_leg_direction()` maps those to short put / short call legs).

---

## 8. Entry, stop, and R definition

From `utils/candle_levels.compute_entry_stop(candle, side, tick_size)`:

| Side | Entry | Stop loss |
|------|-------|-----------|
| **BUY** | `signal.high + tick` | `signal.low − tick` |
| **SELL** | `signal.low − tick` | `signal.high + tick` |

`tick` = product `tick_size` if positive, else `0.01`.

**R** = `|entry − stop_loss|`.

**Targets** (long example; short is symmetric):

- Partial: `entry + partialBookR × R`
- Final (T2): `entry + 20 × R` (default)

Bar-based fill checks (`rwb_engine`):

- Long entry fills when `bar.high >= entry`
- Short entry fills when `bar.low <= entry`
- Long SL when `bar.low <= sl`; short SL when `bar.high >= sl`
- Long target when `bar.high >= target`; short target when `bar.low <= target`

---

## 9. Pre-entry filters

### 9.1 Minimum SL distance

**Purpose:** Reject setups where the wedge is so tight that max-risk sizing inflates contract count and **fees dominate** net PnL.

| Setting | Default | Behavior |
|---------|---------|----------|
| `minSlDistance` | `50` | Skip signal when `|entry − stop| < minSlDistance` |

- Set to `0` to disable.
- Measured in **price points** (e.g. $50 on BTCUSD).
- Backtest: event `rejected:sl_distance:{pattern}` in `events[]`.
- Live: `signal_rejected`, `rejectReason: sl_distance_too_small`.

### 9.2 H1 unmitigated swing filter (optional)

**Purpose:** Require structural confluence — the signal wick must sit near an active **H1 unmitigated swing** level before placing entry.

| Setting | Default | Behavior |
|---------|---------|----------|
| `useSwingFilter` | `false` | When enabled, apply proximity gate after pattern + min SL checks |
| `swingProximityBufferPct` | `0.05` | Max distance as **percent** of swing level: `abs(wick − level) / level × 100` |

**Pre-calculation (before 1m loop):**

1. Fetch native Delta **`1h`** candles for the backtest/live window (+ lookback, default **14 days**).
2. Run `calculate_unmitigated_levels()` and `build_swing_level_lookup()` — a map from Delta 1h open time → active unmitigated highs/lows.

Delta native `1h` candles use **UTC hour boundaries**, which appear as **:30 IST** opens on charts (not IST calendar `:00` hours). Wick Break maps each 1m signal to its parent bucket via `delta_h1_bucket_open()`.

**Gate rules (after RWB confirm, before order):**

| Pattern | Direction | Wick extreme | Must be near |
|---------|-----------|--------------|--------------|
| Shooting star | LONG | `signal.high` | Unmitigated H1 **high** |
| Hammer | SHORT | `signal.low` | Unmitigated H1 **low** |

**Fail logic:** skip trade; backtest `skipReason: no_swing_proximity`, event `rejected:no_swing_proximity:{pattern}`; live activity `no_swing_proximity`.

**Trade metadata:** `swingLevel` and `distToLevelPct` stored on taken trades and skipped signals for ledger analysis.

**Disabled:** when `useSwingFilter` is false, gate always passes (no H1 fetch required on live beyond optional cache warmup).

---

## 10. Finite-state machine

States (`RwbState`):

| State | Meaning |
|-------|---------|
| `scanning` | Watching for new patterns; no pending order or open position |
| `pending_entry` | SL entry order working at broker (or simulated pending) |
| `manage_trade` | Position open; managing SL, partial, T2 |
| `stopped` | Session ended (live only) |

### 10.1 Scanning guards

Scanning runs only when:

- `state == scanning`
- No open broker position on symbol
- Bar is not inside optional `noTradeStartTime`–`noTradeEndTime` window (IST, supports overnight wrap)

### 10.2 Pending entry replacement (live only)

While `pending_entry`, if a **new same-direction** signal appears with a **better** entry:

- Long: lower entry price
- Short: higher entry price

…the pending order may be cancelled and replaced. New setup must still pass `minSlDistance` and (if enabled) the H1 swing gate.

---

## 11. Entry fill and timeout

| Parameter | Value |
|-----------|-------|
| `FILL_TIMEOUT_BARS` | `5` |

Each new completed 1m bar while pending decrements `pendingBarsLeft`. At zero:

- Live: cancel broker entry, `event: entry_timeout`, return to `scanning`
- Backtest: `entry_timeout` event, return to `scanning`

Fill detection:

- **Backtest:** next bar’s high/low crosses entry
- **Live:** broker position appears or order status indicates fill

---

## 12. Trade management — partial book and final target

### 12.1 Sequence

1. Position filled at `entry` with initial `stopLoss`.
2. Watch for **partial target** at `partialBookR` (default **4R**).
3. On T1 hit: close `partialBookPct` (default **50%**) of **initial** size at partial target price.
4. Move effective stop on remainder to **breakeven** (`entry`).
5. Remainder targets **T2** at **20R** (default).
6. SL on remainder uses breakeven after T1.

### 12.2 Partial size rounding

`partial_exit_quantity(total_size, remaining_size, fraction)`:

- `partial = max(1, floor(total × fraction))`, capped by `remaining`
- Ensures at least 1 contract remains for the second leg when possible

### 12.3 Exit reason codes (ledger)

| `exitReason` | Meaning |
|--------------|---------|
| `sl` | Stop loss (initial or breakeven) |
| `t1_partial` | Partial book at `partialBookR` |
| `t2` | Final target hit |
| `session_end` | Backtest window ended with open position (closed at last bar close) |

Grouped trades in the UI merge legs sharing `entryTime + side + pattern`.

---

## 13. Position sizing

### 13.1 Modes

| `sizingMode` | Behavior |
|--------------|----------|
| `lots` | Fixed `lots` contracts (minimum 1) |
| `max_risk` | `floor(maxRiskAmount / (|entry − SL| × contract_value))`, minimum 1 contract |

Formula (`utils/risk_sizing.compute_position_size`):

```
contracts = max(1, floor(risk / (distance × contract_value)))
```

**Important:** `maxRiskAmount` caps **gross price loss to initial SL**, not net loss after fees. Tight stops → large contract count → high notional → fees can exceed the risk budget on stop-out. Use `minSlDistance` to avoid this.

### 13.2 Live max risk default

If `maxRiskAmount` omitted at session start: `account.riskAmount`, else `100`.

---

## 14. Fees and PnL

### 14.1 Gross leg PnL

```
LONG:  (exit − entry) × size × contract_value
SHORT: (entry − exit) × size × contract_value
```

### 14.2 Taker fee (simulation)

```
fee = rate × (entry_notional + exit_notional) × (1 + GST)
entry_notional = contract_value × size × |entry_price|
exit_notional  = contract_value × size × |exit_price|
```

Defaults: `rate = 0.0005`, `GST = 0.18`.

**Scalper offer** (backtest API only, `scalperOffer: true`): waives exit-leg fee if hold time ≤ 30m (BTC/ETH) or 15m (other symbols).

### 14.3 Net PnL

```
net_pnl = gross_pnl − fee
```

Backtest ledger **PnL** column shows **net** per grouped trade. Expanded row shows fees and per-leg partial/final qty.

---

## 15. Live engine

**Service:** `RwbService` (`rwb_service.py`)  
**Collection:** `rwb_sessions`  
**Runner:** Background asyncio loop per active session; polls 1m candles and broker state.

### 15.1 Session lifecycle

1. `POST /api/rwb/sessions/start` → doc inserted, `state: scanning`
2. On signal → `place_sl_entry` via `RwbExecutionService` → `pending_entry`
3. On fill → `ensure_bracket_protection` (stop + optional TP) → `manage_trade`
4. T1 partial → `execute_t1_partial_exit` at broker; update `bookedPnl`, breakeven stop
5. Flat → `scanning` or `stopped`
6. `POST /api/rwb/sessions/stop` → optional flatten, `state: stopped`

### 15.2 Context fields (`session.context`)

| Field | Purpose |
|-------|---------|
| `orderId` | Pending entry order |
| `pattern` | `hammer` / `shooting_star` |
| `side` | `BUY` / `SELL` |
| `entry`, `stopLoss`, `size` | Working levels |
| `pendingBarsLeft` | Fill countdown |
| `remainingSize` | After partial |
| `t1Filled`, `breakevenSl` | Post-partial state |
| `t2Price` | Final target price |
| `stopOrderId`, `takeProfitOrderId` | Broker bracket legs |
| `lastBarTime` | Dedup bar processing |

### 15.3 PnL on live session

- `bookedPnl` — realized from closed legs (partials, full exits)
- `runningPnl` — mark-to-market on open remainder
- `total_pnl` — sum in API view

### 15.4 Broker safety

- Cancels stale open orders before new entry
- Reconciles unexpected positions while scanning (flatten)
- Private WebSocket stream gated via `execution_guard` while sessions active

---

## 16. Backtest engine

**Service:** `RwbBacktestService.run()` — synchronous `simulate()` on cached 1m bars.

### 16.1 Data prep

When `useSwingFilter` is enabled (or always pre-fetched for consistency), the service loads **15m** candles, builds H1 bars, and constructs the swing level lookup before the 1m simulation loop. Response `dataSource.h1Bars` reports H1 bar count.

### 16.2 Request window

- `startDate` + `startTime` (IST) through `endDate` 23:59 IST
- Product metadata fetched once for `contract_value`, `tick_size`, taker rate

### 16.3 Response shape

| Key | Content |
|-----|---------|
| `strategyId` | `rejection_wick_breakout` |
| `symbol` | Normalized symbol |
| `config` | Full `RwbConfig` used (including `max_risk_amount`, `min_sl_distance`) |
| `summary` | `totalPnl`, `grossPnl`, `totalFees`, `winRate`, `tradeCount`, `skippedBySwingFilter` |
| `trades` | Per-leg records (`initialSize`, `contractValue`, `pnl`, `fee`, `exitReason`, `swingLevel`, `distToLevelPct`, …) |
| `skippedSignals` | Pattern signals rejected by swing filter (`skipReason`, `swingLevel`, `distToLevelPct`) |
| `events` | FSM trace (`signal:…`, `filled:…`, `rejected:sl_distance:…`, `rejected:no_swing_proximity:…`, …) |
| `dataSource.totalBars` | 1m bar count simulated |
| `dataSource.h1Bars` | H1 bars used for swing lookup |

### 16.4 Trade ledger (UI)

Main columns: Entry time, Instrument, Direction, Entry, Exit, **Quantity** (entry contracts), **PnL** (net), **Swing Level**, **Dist to Level %**, **Skip Reason** (skipped-signals table).

CSV export: `utils/backtestExport.js` — summary, year-wise IST returns, full trade list, skipped signals.

---

## 17. Configuration reference

| Field | API alias | Default | Live UI | Backtest UI |
|-------|-----------|---------|---------|-------------|
| Symbol | `symbol` | `BTCUSD` | Yes | Yes |
| Timeframe | `timeframe` | `1m` | Yes (`1m`/`5m`/`15m`) | Yes |
| Sizing mode | `sizingMode` | `max_risk` | Yes | Yes |
| Lots | `lots` | `1` | If lots mode | If lots mode |
| Max risk | `maxRiskAmount` | `100` | Yes | Yes |
| Partial book R | `partialBookR` | `4` | Yes (4 or 6) | Yes (4 or 6) |
| Partial book % | `partialBookPct` | `0.5` | Yes (1–99 UI → ÷100) | Yes |
| Min SL distance | `minSlDistance` | `50` | Yes | Yes |
| H1 swing filter | `useSwingFilter` | `false` | Yes (toggle) | Yes (toggle) |
| Swing proximity % | `swingProximityBufferPct` | `0.05` | Yes (if filter on) | Yes (if filter on) |
| Final target R | `target2R` | `20` | Fixed at start | Fixed in engine |
| No-trade window | `noTradeStartTime`, `noTradeEndTime` | — | API only | API only |
| Scalper offer | `scalperOffer` | `false` | — | API only |

---

## 18. REST API

Base path: `/api/rwb`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/meta` | Strategy id, defaults (`partialBookRDefault`, `minSlDistanceDefault`, `finalTargetR`, …) |
| POST | `/backtest/run` | Sync backtest |
| GET | `/sessions` | All user sessions |
| GET | `/sessions/active` | Non-stopped sessions |
| POST | `/sessions/start` | Start live scanner |
| POST | `/sessions/stop` | Stop session (`sessionId`, optional `closePosition`) |

### 18.1 `POST /backtest/run` body

```json
{
  "symbol": "BTCUSD",
  "startDate": "2026-01-01",
  "startTime": "00:00",
  "endDate": "2026-01-31",
  "sizingMode": "max_risk",
  "maxRiskAmount": 5,
  "partialBookR": 4,
  "partialBookPct": 0.5,
  "minSlDistance": 50,
  "useSwingFilter": true,
  "swingProximityBufferPct": 0.05
}
```

### 18.2 `POST /sessions/start` body

Same sizing / partial / `minSlDistance` / swing filter fields. `maxRiskAmount` optional (falls back to account risk).

---

## 19. WebSocket

| Topic | Payload |
|-------|---------|
| `session` + `type: rwb_session` | `{ session: { id, symbol, state, context, activities, booked_pnl, running_pnl, … } }` |

Published on session create, state change, activity append, PnL update.

---

## 20. MongoDB

**Collection:** `rwb_sessions`

| Field | Type | Notes |
|-------|------|-------|
| `userId` | string | Owner |
| `accountId` | string | Delta account |
| `symbol` | string | e.g. `BTCUSD` |
| `sizingMode`, `lots`, `maxRiskAmount` | — | Sizing config |
| `partialBookR`, `partialBookPct` | float | Partial ladder |
| `minSlDistance` | float | Min SL filter |
| `useSwingFilter` | bool | H1 swing gate |
| `swingProximityBufferPct` | float | Swing proximity % (default 0.05) |
| `target2R` | float | Default 20 |
| `tickSize`, `contractValue` | float | From product |
| `state` | string | FSM state |
| `context` | object | Working trade state |
| `activities` | array | Append-only log |
| `bookedPnl`, `runningPnl` | float | Session PnL |
| `createdAt`, `updatedAt` | datetime | UTC |

Indexes: `(userId, state)`, `(userId, createdAt)`.

---

## 21. Frontend flows

**Route:** Wick Break nav → `RwbPage`

| Tab | Content |
|-----|---------|
| **Live** | Start modal (**Structural Confluence**: H1 swing toggle + proximity %), session status strip, PnL panel, position prices, activity feed |
| **History** | Stopped sessions cards |
| **Backtest** | Backtest modal (structural confluence settings), summary cards, equity curve, year-wise table, trade ledger + skipped signals |

**Components:** `frontend-react/src/components/rwb/*`

Live requires a **selected Delta account**. Symbol live prices subscribed via `subscribeLiveSymbol(symbol, 'rwb')`.

---

## 22. Reject and activity reason codes

### 22.1 Pattern structure (`rejectReason` on live)

| Code | Pattern |
|------|---------|
| `C-3 must be the structural low` | Hammer |
| `Hammer low must stay above C-3 low` | Hammer |
| `C-2 low must stay above C-3 low` | Hammer |
| `C-1 low must stay above C-3 low` | Hammer |
| `C-3 must be the structural high` | Shooting star |
| `Shooting star high must stay below C-3 high` | Shooting star |
| `C-2 high must stay below C-3 high` | Shooting star |
| `C-1 high must stay below C-3 high` | Shooting star |

### 22.2 Pre-entry filters

| `rejectReason` | When |
|----------------|------|
| `sl_distance_too_small` | `|entry − SL| < minSlDistance` |
| `no_swing_proximity` | H1 swing filter on; wick not within buffer of matching unmitigated level |
| `invalid_position_size` | Risk sizing error |
| `stale_open_orders` | Could not cancel conflicting orders |
| `entry_order_failed` | Broker reject |

### 22.3 Backtest events (sample)

`signal:hammer`, `filled:hammer`, `t1_hit_be`, `position_closed`, `rejected:sl_distance:hammer`, `rejected:no_swing_proximity:hammer`, `entry_timeout`

### 22.4 Live activity `event` types (sample)

`scanning`, `signal`, `signal_rejected`, `entry_order_placed`, `entry_order_filled`, `entry_timeout`, `t1_partial`, `breakeven`, `stop_order_placed`, `failed`, `stopped`, `broker_cleanup`

---

## 23. Live vs backtest parity

| Aspect | Backtest | Live |
|--------|----------|------|
| Bar source | Cached 1m REST | Cached 1m + runner poll |
| Entry | Bar high/low cross | Broker SL order fill |
| Partial / T2 | Bar touch | Bar touch + live price for T1; broker orders for exits |
| Fees | Simulated taker + GST | Broker actuals (not re-simulated in session PnL) |
| Timeout | 5 bars | 5 bars + broker cancel |
| Replace pending | No | Yes (better same-direction entry) |
| `minSlDistance` | Yes | Yes |
| `scalperOffer` | API only | No |

---

## 24. Edge cases and limitations

- **Fees vs max risk:** Max risk sizes gross SL only; net stop-out loss can exceed `maxRiskAmount` when notional is large. Raise `minSlDistance` or lower `maxRiskAmount`.
- **Minimum 1 contract:** `compute_position_size` never returns &lt; 1 even if risk math says fractional.
- **Session end (backtest):** Open positions closed at last bar **close**, not at SL/T2.
- **One symbol per session:** No portfolio-level coordination across symbols.
- **No-trade window:** API-supported; not exposed in current modals.
- **Directional Options:** Separate codebase path; shared only `candle_patterns.py` geometry.

---

## 25. Troubleshooting FAQ

**Why is quantity huge but max risk is small?**  
Tight SL → many contracts to risk the same dollars. Check `minSlDistance` and the expanded row SL distance.

**Why is PnL much larger than max risk on a loser?**  
PnL is **net of fees**. Large contract count on tight stops creates high notional fees. Gross move to SL may still be ≈ max risk.

**Why don’t I see trades in backtest?**  
Many 1m wicks fail structure or `minSlDistance`. Inspect `events[]` for `rejected:sl_distance` counts.

**Shooting star but SHORT?**  
Wick Break maps shooting stars to **LONG** (BUY). A short on a shooting star indicates stale code or a session started before the direction fix.

**Hammer but LONG?**  
Wick Break maps hammers to **SHORT** (SELL). Same as Directional Options short-call bias.

**Does live keep running if I close the browser?**  
Yes. Session runs on server until stopped.

---

## 26. Source file map

| Area | Path |
|------|------|
| FSM + simulate | `backend-python/cryptobridge/services/rwb_engine.py` |
| Live runner | `backend-python/cryptobridge/services/rwb_service.py` |
| Broker orders | `backend-python/cryptobridge/services/rwb_execution.py` |
| Backtest API | `backend-python/cryptobridge/services/rwb_backtest_service.py` |
| HTTP routes | `backend-python/cryptobridge/routers/rwb.py` |
| Patterns | `backend-python/cryptobridge/utils/candle_patterns.py` |
| Entry/SL | `backend-python/cryptobridge/utils/candle_levels.py` |
| Risk sizing | `backend-python/cryptobridge/utils/risk_sizing.py` |
| UI | `frontend-react/src/components/rwb/` |
| Tests | `backend-python/tests/test_rwb.py` |

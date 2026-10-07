# CryptoBridge — Complete Feature Reference

**Version:** 0.2.0  
**Last updated:** 2026-07-24  

This document is the **single complete inventory** of CryptoBridge functionality on the `arbitrage` branch. When anything changes, update this file and [CHANGELOG.md](./CHANGELOG.md) per [DOCUMENTATION-POLICY.md](./DOCUMENTATION-POLICY.md).

> **Current UI (2026-07-24):** Post-login pages: **Dashboard**, **Execution**, **ST Options**, and **Active Positions**. Core backend: auth, accounts, orders, positions, live prices, spot-triggered execution (`spot_sl_monitors`), and **1H ST Options** (`st_options_*`).

---

## Table of contents

1. [Product overview](#1-product-overview)
2. [Authentication](#2-authentication)
3. [Accounts & wallet](#3-accounts--wallet)
4. [Live market data](#4-live-market-data)
5. [Dashboard (landing page)](#5-dashboard-landing-page)
6. [Order API (backend only)](#6-order-api-backend-only)
7. [Arbitrage — funding rates](#7-arbitrage--funding-rates)
8. [Spread Execution](#8-spread-execution)
9. [Rejection Wick Breakout (1m Perps)](#9-rejection-wick-breakout-1m-perps)
10. [SuperTrend Pullback Scaler (SPS)](#10-supertrend-pullback-scaler-sps)
10b. [SuperTrend Perp (ST Perp)](#10b-supertrend-perp-st-perp)
10. [Move Fade Writer](#10-move-fade-writer)
11. [BTC MV Straddle Buy (Backtest)](#11b-btc-mv-straddle-buy-backtest)
12. [Strike Advisor (ML)](#11a-strike-advisor-ml)
12b. [1H SuperTrend Options Sell (ST Options)](#12b-1h-supertrend-options-sell-st-options)
13. [REST API reference](#12-rest-api-reference)
14. [WebSocket protocol](#13-websocket-protocol)
15. [Data model (MongoDB)](#14-data-model-mongodb)
16. [Background jobs](#15-background-jobs)
17. [Configuration](#16-configuration)
18. [Frontend structure](#17-frontend-structure)
19. [Tests](#18-tests)

---

## 1. Product overview

CryptoBridge is a minimal **multi-exchange trading foundation** focused on arbitrage:

- **Local auth** (email/password)
- **Multiple Delta Exchange India accounts** per user (API key + secret, encrypted at rest)
- **Portfolio dashboard** as the post-login landing page (balances, ST Options equity curve + recent trades)
- **Live prices + margin** over a trimmed WebSocket feed
- **Arbitrage Phase 1:** real-time Delta perpetual funding rates (WebSocket-driven)

**Stack:** React 18 + Vite (frontend), FastAPI + Motor (backend), MongoDB.

**Branding:** logo and favicon use `frontend-react/public/Cryptobridge.svg`, rendered via shared `CryptoBridgeLogo` (`components/workspace/CryptoBridgeLogo.jsx`, source constant `CRYPTOBRIDGE_LOGO_SRC` in `documentTitle.js`). Surfaces: workspace header, login/register panel, settings modal, system footer, browser tab favicon (`index.html`), and `/docs/calendar-spread-dynamic-sizing.html`. The browser tab title is `CryptoBridge` when flat, or `CryptoBridge :: +123.45` (signed running unrealized P/L from open Delta positions, or calendar-spread running PnL when no broker legs are open).

**Pages** (post-login, `App.jsx` `currentPage`):

| Page ID | Label | Component |
|---------|-------|-----------|
| `dashboard` | Dashboard | `DashboardPage` |
| `execution` | Execution | `ExecutionPage` — option search with live premiums, selected-option panel, spot-triggered sell + monitor |
| `st-options` | ST Options | `StOptionsPage` — 1H SuperTrend + EMA options sell (Live Running/History + Backtest) |
| `positions` | Active Positions | `ActivePositionsPage` |

Terminal `state` holds only `watchList` (live price symbols + open position underlyings) and `fsmEngines` (open position FSM metadata for the positions view).

**Header:** workspace top-nav with `CryptoBridgeLogo` (SVG + wordmark), nav strip, BTC/ETH live chips, connection dot, account selector, theme toggle, settings gear, logout.

**Account Settings modal:** fixed-size sidebar layout (Profile Settings, Trading Account, Arbitrage, Spread Execution, API) with gradient banner — the modal keeps the same dimensions across all sections and scrolls internally. Trading Account shows connected exchange cards with balance and select/delete; Arbitrage selects the per-exchange account used for arbitrage trading via brand-logo-labelled selectors (defaults to the sole account on an exchange); Spread Execution configures the execution parameters.

---

## 2. Authentication

### User flows

- **Register:** display name, email, password (≥ 8 chars) → session token in `localStorage` (`cryptobridge.token`)
- **Login:** email + password → new browser session token
- **Logout:** `POST /api/auth/logout`, clears token, closes WebSocket
- **Logout all:** `POST /api/auth/logout-all`
- **Sessions:** up to **6 concurrent** browser sessions per user (`app_sessions`, UUID bearer, 7-day sliding TTL)

### Security

- Passwords hashed with bcrypt
- API secrets encrypted with Fernet (`CRYPTOBRIDGE_ENCRYPTION_KEY`)
- All trading routes require `Authorization: Bearer <token>` or `?token=` on WebSocket

---

## 3. Accounts & wallet

### Add account

`POST /api/accounts` with:

| Field | Description |
|-------|-------------|
| `label` | User-defined name |
| `apiKey` | Exchange API key |
| `apiSecret` | Exchange API secret |
| `exchange` | `delta` (default; only supported value) |

- **Delta:** credentials validated via `fetch_profile`; wallet/margin enrichment via Delta REST

### Manage accounts

- List: `GET /api/accounts`
- Delete: `DELETE /api/accounts/{id}`
- Select active account: `POST /api/accounts/{id}/select`
- Frontend **Manage Account** modal: Delta-only; IP-whitelist card for Delta API keys

### Collection

Accounts stored in `delta_accounts` with `exchange: "delta"`.

---

## 4. Live market data

### Delta public prices

- Backend `DeltaMarketDataService` subscribes to Delta public WebSocket for baseline symbols
- Prices cached in memory and relayed to clients

### REST bootstrap

- `GET /api/live/prices` — diagnostic tick map + market status (not used by the app UI; live prices stream over `/ws/live` only)

### WebSocket (trimmed)

See [§8 WebSocket protocol](#8-websocket-protocol). Snapshot includes accounts, prices, open orders (Delta selected account).

### Analysis (market scanner)

**Page:** `AnalysisPage` (nav **Analysis**) with three tabs — **Top Gainers** (default), **Highest Funding**, and **Near ATH**.

#### Top Gainers tab

- **Cards:** Delta perpetuals ranked by **24h % gain**; each card shows coin + symbol, 24h change, current price, current **funding rate**, and the **funding-rate change over the last ~8h** with a trend arrow (`rising` / `falling` / `flat`).
- **Funding pill:** flags coins whose funding is **favorable** — positive, or negative-but-rising over the window (`funding_favorable`).
- **Backend:** `MarketInsightsService.top_movers(limit, funding_window_hours)` reads perp tickers (24h change from `open`/`close`, fallback `mark_change_24h`), takes the top-N gainers, and for those fetches Delta **funding history candles** (`FUNDING:<symbol>`, resolution `1h`, cached 15m TTL, bounded concurrency) to compute `fundingPct`, `fundingPctAgo`, `fundingChangePctPts`, `fundingFavorable`, `fundingTrend`.
- **Route:** `GET /api/market/movers?limit=20&fundingWindowHours=8` → `{ limit, fundingWindowHours, evaluatedCount, coins: [{ coin, symbol, currentPrice, changePct24h, fundingPct, fundingPctAgo, fundingChangePctPts, fundingFavorable, fundingTrend }] }` (coins sorted descending by `changePct24h`).

#### Highest Funding tab

- **Cards:** Delta perpetuals ranked by **funding rate normalized to a per-8h basis** (highest/most-positive first). Each contract funds at its native interval (1h/4h/8h); the raw ticker `funding_rate` is per that interval, so it is normalized as `per8h = perInterval × (8 / intervalHours)` for an apples-to-apples ranking.
- **Each card:** coin + symbol, the **per-8h funding %** (headline), the **native rate** and **funding interval** badge, current price, and a live **next-funding countdown**.
- **Backend:** `MarketInsightsService.highest_funding(limit)` reads perp tickers + funding intervals (`fetch_perpetual_funding_intervals`), normalizes each coin's funding to per-8h via the shared arbitrage helpers (`delta_funding_fraction`, `normalize_to_8h`, `fraction_to_pct`, `next_funding_ts`), and sorts descending. Contracts with no funding rate are skipped.
- **Route:** `GET /api/market/highest-funding?limit=30` → `{ limit, normalizationBasis, evaluatedCount, coins: [{ coin, symbol, fundingPct, fundingPer8hPct, intervalHours, nextFundingTs, currentPrice }] }` (coins sorted descending by `fundingPer8hPct`).

#### Near ATH tab

- Scans all Delta perpetual futures and shows, as coin cards, those trading **within N% of their all-time high** (threshold selector: 5 / 10 / 15 / 25%, default 5%).
- **Each card:** coin + Delta symbol, current price, all-time high price, **% below ATH** (a proximity bar; “At high” when at/above), and the date the ATH was reached.
- **Backend:** `MarketInsightsService.near_ath(thresholdPct)` derives each coin's ATH from **weekly** Delta candles (`fetch_candles`, resolution `1w`) — one request per symbol covers years of history; the max weekly high is the ATH. ATH is cached per symbol (6h TTL); current price comes fresh from the perp ticker feed each call, and a live price above the cached high is treated as a new high. "All-time high" is bounded by the candle history Delta serves for that contract.
- **Route:** `GET /api/market/near-ath?thresholdPct=5` → `{ thresholdPct, evaluatedCount, withinCount, coins: [{ coin, symbol, currentPrice, athPrice, dropFromAthPct, athTime, atNewHigh, withinThreshold }] }` (coins sorted ascending by `dropFromAthPct`).

---

## 5. Dashboard (landing page)

Post-login default view (`DashboardPage`). Portfolio-style layout wired to live account balances and **closed ST Options** trade history (cursor-paged `GET /st-options/history` at 100 per page, up to 200 closes for equity curve / recent trades) plus **`GET /positions/open`** REST fallback for Active Option Desks when the live WS has not delivered positions yet.

### Account scope

- **All accounts (cumulative):** sums available margin / equity across every connected exchange account (USD/USDT-comparable).
- **Individual account:** shows balance for the selected account only.

### Widgets

| Widget | Data source |
|--------|-------------|
| KPI row | Account equity / margin + open broker positions |
| Equity Performance Wave | Interactive cumulative closed ST Options P&L (1W / 1M / All); zero line, win/loss markers, hover tooltip; stats: Total P&L, win rate, max drawdown, trade count |
| Recent Trades | Latest closed ST Options trades — quantity (lots), square-off time (IST) + PnL |
| Accounts list | Connected exchange accounts |
| Open Positions preview | Live open broker positions (`WS type: positions` or REST `/positions/open`) |

---

## 6. Order API (backend only)

The manual order ticket UI has been removed. Delta order placement REST endpoints remain for integrators:

- `POST /api/orders`, `GET /api/orders/active`, `POST /api/orders/{id}/cancel`

Uses selected Delta account credentials when called directly.

### Request shape (`POST /api/orders`)

```json
{
  "symbol": "BTCUSD",
  "side": "BUY",
  "orderType": "LIMIT",
  "size": 10,
  "entry": 60000
}
```

Uses selected Delta account credentials.

---

## 7. Arbitrage — funding rates

### Purpose

Monitor **Delta** perpetual futures funding rates (`GET /v2/tickers?contract_types=perpetual_futures` + public WS `funding_rate` channel).

### Normalization

| Field | Interval source | Interpretation |
|-------|-----------------|----------------|
| `funding_rate` | `product_specs.rate_exchange_interval` (seconds) from `/v2/products` — contract-specific 1h/4h/8h | Percent charged per the contract's native interval (e.g. `0.01` = 0.01% per interval) |

Each row carries `deltaNextFundingTs` (unix seconds) — the next UTC interval boundary (`next_funding_ts`). The frontend renders a live countdown.

Rates are normalized to **per-8h percent**: `per8h = perInterval × (8 / intervalHours)`.

### Update model

**Delta funding is event-driven over WebSocket.** `DeltaMarketDataService` subscribes the public `funding_rate` channel for every perpetual and keeps a `latest_funding` cache; `ArbitrageService` rebuilds + broadcasts the `arbitrage_funding` snapshot on each change (bursts coalesced within ~1s). Delta perpetual metadata + funding intervals are bootstrapped once (and refreshed every ~10min) via REST.

### Frontend (`ArbitragePage`)

- Initial load: `GET /api/arbitrage/funding`
- Live updates: WebSocket `arbitrage_funding` messages
- **Top 6 as cards:** responsive grid showing the 6 coins with the highest absolute per-8h funding
- Each card: coin badge, per-8h funding %, native interval badge, next-funding countdown, Delta symbol
- Sortable table: Coin, Delta funding % + interval + symbol, per-8h %, next funding

### Opportunities tab

Detects **negative funding** on **BCH** and **ETC** on Delta.

**Strategy:** long the alt (BCH or ETC) and short **equal-notional** BTC or ETH (BCH↔BTC, ETC↔ETH) on Delta. Real limit orders on both legs.

**Backend:** `OpportunityService` reads `ArbitrageService` snapshot rows; `utils/opportunity_helpers.py` for pair map, negative-funding selection, notional-matched hedge sizing, and required margin. Persists executions in `opportunity_trades`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/arbitrage/opportunities` | List active BCH/ETC negative-funding opportunities |
| POST | `/arbitrage/opportunities/quote` | Quote alt+hedge legs: qty, notional, required vs available margin, cashflow, fees/slippage, liquidation, interval alignment |
| POST | `/arbitrage/opportunities/execute` | Place both legs (long alt, short hedge) on Delta |
| GET | `/arbitrage/opportunities/history` | List executed opportunity trades (recent first) |
| POST | `/arbitrage/opportunities/close` | Market-close both legs of an open opportunity trade |

**Quote/execute body:** `accountId`, `exchange` (`delta`), `altCoin` (`BCH` \| `ETC`), `altQty`, `leverage`. **Close body:** `tradeId`.

**Frontend:** `ArbitragePage` has **Spreads** and **Opportunities** tabs. On **Spreads**, an **Auto Execute** toggle and per-card **Arbitrage** button. `OpportunitiesTab` shows opportunity cards and **Execute Opportunity** modal (Delta account, quantity/leverage, margin bar, confirm).

---

## 8. Spread Execution

Delta funding spread execution.

### Behavior

- **Direction:** from signed funding spread (`delta_side_from_spread`)
- **Leverage:** target (default 10×) capped to Delta max
- **Auto position size:** `margin = availDelta × autoMarginPct` (default 50%); per-card **Arbitrage** button uses `manualMarginPct` (default 20%)
- **Entry:** Delta best bid/ask via `build_trade_leg_plan`
- **Auto exit:** `holdUntilTs = nextFundingTs + holdAfterFundingSec` (default 120s)
- **One auto position at a time**
- Poll/manage loop every **10s**; status broadcast as `spread_execution` over WebSocket

### Frontend

- **Spreads tab (`ArbitragePage`):** Auto Execute toggle; per-card **Arbitrage** button
- **Active Positions (`ActivePositionsPage`):** unified view across **all connected Delta accounts**. **Open** tab: app spread-trade cards plus standalone broker positions and **open orders**. **Past Orders** tab: Delta order history. Live merge via WebSocket `type: positions` over REST `GET /api/positions/open`. Sync: Delta private WS (`positions` + `orders` with `symbols: ["all"]`; snapshot/delete/zero-size handled) plus **public mark ticks** for every open position symbol (options and perps) so running PnL updates on each market tick; **15s MTM refresh** also re-fetches positions/orders from REST as a fallback when WS drops or lags. For Delta **option** legs (`C-*`/`P-*`) running PnL is recomputed mark-to-market to match the exchange UPNL column. **Payoff chart:** select one or more open rows and click **Payoff** — when both legs of an open calendar spread are selected, the chart reuses the strategy’s WS payoff (frozen target/stop lines when applicable); otherwise a two-leg calendar pair (same strike/type, short near + long far) is auto-detected and modeled at **near-leg expiry** (intrinsic short + Black–Scholes far); other selections use mark-to-market Black–Scholes curves with correct contract scaling.
- **Account Settings — Arbitrage:** Delta account selector used for arbitrage trading and Calendar Spread live orders
- **Account Settings — Spread Execution:** editable params (auto/manual margin %, target leverage, hold-after-funding seconds, liq buffer %)

### REST

| Method | Path | Description |
|--------|------|-------------|
| GET | `/arbitrage/spread/status` | Config + auto status + open positions (per-exchange PnL/funding) + open running PnL / cashflow / fund inflow totals |
| PATCH | `/arbitrage/spread/config` | Update spread execution settings |
| POST | `/arbitrage/spread/auto` | `{ enabled }` — toggle Auto Execute |
| POST | `/arbitrage/spread/execute` | `{ coin }` — manual spread open (20% margin) |
| POST | `/arbitrage/spread/close` | `{ tradeId }` — manual close both legs |

### WebSocket

| `type` | Description |
|--------|-------------|
| `spread_execution` | Spread config, auto running flag, open positions, fund inflow totals |

### MongoDB

| Collection | Purpose |
|------------|---------|
| `spread_exec_config` | Per-user spread settings (`autoEnabled`, account IDs, margin %, leverage, hold-after-funding, liq buffer) |
| `spread_trades` | Persisted spread trades (open/closed/failed) with `source` (auto/manual), `holdUntilTs`, liquidation, PnL, funding |

---

## 9. Rejection Wick Breakout (1m Perps)

**Vanilla RWB** on **BTCUSD/ETHUSD perp futures** — hammer/shooting-star geometry + C3 structure on **1m, 5m, or 15m** bars (configurable). No EMA, confluence, or options filters. Optional **H1 unmitigated swing** proximity gate.

**Full strategy reference:** [rejection-wick-breakout.md](./rejection-wick-breakout.md) — complete business logic + technical spec (pattern geometry, structure rules, FSM, entry/SL, min SL distance, H1 swing filter, partial book, 20R target, sizing, fees, live/backtest, API, Mongo, FAQ).

### Strategy

- Shooting star → **LONG** (entry 1 tick above wick high; SL 1 tick below wick low)
- Hammer → **SHORT** (entry 1 tick below wick low; SL 1 tick above wick high)
- Partial book at configurable `partialBookR` / `partialBookPct`; remainder targets **20R**; fill timeout **5 bars**
- **Min SL distance:** skip setups when `|entry − stop|` is below `minSlDistance` (default **50** points)
- **H1 swing filter (optional):** when `useSwingFilter` is enabled, valid RWB geometry must also sit within `swingProximityBufferPct` (default **0.05%**) of a Delta native **1h** unmitigated swing high (shooting star) or low (hammer); skip reason `no_swing_proximity`. H1 data fetched directly via REST `resolution=1h` (no 15m aggregation).

### UI

**Wick Break** nav page — Live / History / Backtest. Settings: symbol, **timeframe (1m / 5m / 15m)**, lots or max risk, partial book R (4 or 6), partial book %, **min SL distance (points)**, **Structural Confluence** (H1 swing toggle + proximity buffer %).

Backtest trade ledger columns: entry time, instrument, direction, entry, exit, **quantity (contracts)**, **net PnL** (after Delta taker fees + GST), **swing level**, **dist to level %**, **skip reason** (skipped-signals table). Expanded row shows pattern, stop, fees, partial/final exit legs, and coin equivalent when applicable.

### API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/rwb/meta` | Strategy defaults |
| POST | `/api/rwb/backtest/run` | Sync 1m backtest |
| GET | `/api/rwb/sessions` | All sessions |
| GET | `/api/rwb/sessions/active` | Active sessions |
| POST | `/api/rwb/sessions/start` | Start live scanner |
| POST | `/api/rwb/sessions/stop` | Stop session |

### WebSocket

| Topic | Payload |
|-------|---------|
| `session` + `type: rwb_session` | Live session state, activities, PnL |

### MongoDB

| Collection | Purpose |
|------------|---------|
| `rwb_sessions` | Per-user live session state, partial-book config, trade context |

---

## 10. SuperTrend Pullback Scaler (SPS)

**Live execution + backtest** — tabbed workspace at nav **ST Pullback** (`sps` page ID): **Live Engine | Trade History | Backtest Lab** (Calendar Spread workspace chrome).

**Full strategy reference:** [supertrend-pullback-scaler.md](./supertrend-pullback-scaler.md)

### Strategy

- **Underlyings:** BTC, ETH (perp `BTCUSD` / `ETHUSD` as spot reference)
- **Signal timeframe:** **90m** closed bars (15m → IST-aligned aggregation; see §9 / `candle_aggregate.py`)
- **Indicators:** EMA(20) SMA-seed; SuperTrend(8,3) on **HL2** (TV default) with RMA ATR and Pine state-machine flips; computed on **120 days** of 90m history before the visible window (`utils/sps_indicators.py`)
- **Entry (100%):** ST flip **arms** watch; enter on first **1m** candle in the 90m bucket where price **taps** prior closed bar’s SuperTrend line (PUT: `low <= ST`; CALL: `high >= ST`). Entry premium from **1m option** at tap time; `entryTapTime` on live trades.
- **Concurrency:** One open trade per direction; opposite-direction setups allowed while the other side is open
- **Strike / expiry:** ITM-only waterfall from ST — anchor on grid (ETH ÷20, BTC ÷200), up to +2 ITM steps, min **1% spot** premium; **T+2** then **T+3** fallback (`utils/sps_option_resolver.py`)
- **Management:** Premium-only exits — SL **1.5×** entry, TP **0.1×** entry on 15m option candles

### Backend

- `SpsEngine` FSM + `simulate()` with injected `resolve_entry` (`services/sps_engine.py`)
- `SpsService` live runner + async `submit_backtest` / `backtestJob` on WS (`services/sps_service.py`)
- `SpsBacktestService` — 1m spot for tap detection, 1m entry + 15m exit option candles, `diagnostics.stTapPass` (`services/sps_backtest_service.py`)
- Shared option helpers: `utils/options_trade_helpers.py`

### Frontend (`SpsPage`)

- **Live Engine** — Settings panel, **Start Engine** / **Stop Engine** (exit checkbox), KPI strip (scanner / EMA / ST), collapsible trade summary, **Leg Monitor** table; `Live Engine · ON` / position count on sub-tab
- **Trade History** — cumulative equity curve, KPI cards, expandable run panels; refresh + WS-driven reload
- **Backtest Lab** — config summary StatBoxes, **Open backtest setup** modal (`max-w-5xl`), async job banner with **live WS trace/progress** (`backtestJob` on `sps_session`), performance snapshot, equity curve, **90m bar ledger** (OHLC + HL2 + EMA + ST tap level / tap time + ST upper/lower/line per closed bar), paginated trade ledger with exit premium + reason, trace log
- Workspace chrome: `pageShell`, `WorkspaceSubTabs`, `WorkspaceCard`, `WorkspaceDataTable`, `StrategyEquityCurve` (Calendar Spread pattern)

### REST

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sps/meta` | Strategy defaults (quantity, premium exit multipliers) |
| POST | `/sps/start` | `{ symbol, quantity }` |
| POST | `/sps/stop` | `{ symbol, closePositions?: bool }` |
| GET | `/sps/live` | Setups + active legs + indicators + `backtestJob` |
| GET | `/sps/backtest/job` | Lightweight async backtest job poll (`backtestJob` only) |
| GET | `/sps/history` | Trade history (200 rows) |
| POST | `/sps/backtest` | Async backtest job |
| POST | `/sps/backtest/run` | Alias → async submit |

### WebSocket

| `type` | Description |
|--------|-------------|
| `sps_session` | `setups[]`, `active[]`, `backtestJob` (streams progress/trace while processing), last-bar EMA/ST snapshot |

### MongoDB

| Collection | Purpose |
|------------|---------|
| `sps_setups` | Per-user scanner config |
| `sps_trades` | Live scaled short-option legs |

**Legacy:** `directional_options_setups`, `directional_options_trades`, `directional_options_backtest_config` — no longer written; historical data preserved.

---

## 10b. SuperTrend Perp (ST Perp)

**Live execution + backtest** — nav **ST Perp** (`st-perp` page ID): **Live Engine | Trade History | Backtest Lab** (same workspace chrome as SPS).

**Full strategy reference:** [supertrend-perp.md](./supertrend-perp.md)

### Strategy

- **Underlyings:** BTC, ETH perps (`BTCUSD` / `ETHUSD`)
- **Signal:** 90m SuperTrend flip arms direction; **1m wick tap** marks ST; **1m close confirm** triggers market entry
- **Sizing:** `maxRiskAmount` per trade → contract count from entry-to-SL distance; **skips** when 1 contract would exceed max risk
- **SuperTrend:** configurable `stPeriod` (default 8) and `stMultiplier` (default 3.0) on 90m bars
- **Exits:** configurable partial % at `target3r` / `target10r`; runner on opposite 90m ST flip (`exitOnStFlip`); SL at confirm candle H/L (`minSlDistanceUsd`, default $1)

### REST

| Method | Path | Description |
|--------|------|-------------|
| GET | `/st-perp/meta` | Defaults |
| POST | `/st-perp/start` | `{ symbol, maxRiskAmount, minSlDistanceUsd?, stPeriod?, stMultiplier?, partial3rPct?, partial10rPct?, target3r?, target10r?, exitOnStFlip? }` |
| POST | `/st-perp/stop` | `{ symbol, closePositions? }` |
| GET | `/st-perp/live` | Setups + active + `backtestJob` |
| GET | `/st-perp/backtest/job` | Async job poll |
| GET | `/st-perp/history` | Trade history |
| POST | `/st-perp/backtest` | Async backtest (same strategy fields as start) |

### WebSocket

| `type` | Description |
|--------|-------------|
| `st_perp_session` | `setups[]`, `active[]`, `backtestJob`, indicator snapshot |

### MongoDB

| Collection | Purpose |
|------------|---------|
| `st_perp_setups` | Per-user scanner (risk, ST period/multiplier, exit plan) |
| `st_perp_trades` | Live perp positions |

---

## 10. Move Fade Writer

**Delta-only** — backtest and move study (no live orders in phase 1). See [move-fade-writer.md](./move-fade-writer.md).

**Page:** `MoveFadeWriterPage` (nav **Move Fade**) with **Move Study** and **Strike Ladder** tabs.

### Strategy rules

- Daily anchor = BTC at **6:30 PM IST**; monitor next 24h for separate **up** and **down** move thresholds (e.g. 4.5% / 6%).
- First threshold touch **locks in** side (up → short CALL, down → short PUT); entry at **next Delta hourly close** (**:30** UTC).
- Expiry = nearest Delta BTC expiry after entry; if entry **after 9:00 AM IST**, use **next day's** expiry.
- **SL** 130% of entry premium; **TP** 80% decay (20% of entry); **one re-entry** after SL on same contract.
- Backtest sweeps **ITM10…ATM…OTM10**; live default **OTM5** highlighted in UI.

### APIs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/move-fade/move-study` | Move distribution + trigger stats from anchor |
| POST | `/move-fade/backtest` | Strike-ladder historical simulation (real option candles) |

---


## 11b. BTC MV Straddle Buy (Backtest)

Long **MV straddle** on Delta BTC/ETH MOVE products: user **startTime** / **stopTime** (defaults **18:30** / **22:30 IST**), MV product expiry from startTime (evening → next day, morning → same day), 5m `MARK:MV-*` candles, shooting-star below 5 EMA, buy-stop entry, 6R/20R scaling, 2 full-SL daily halt. See [move-straddle.md](./move-straddle.md).

### Frontend (`MoveStraddlePage`)

- **Backtest | Live | History** tabs (same chrome as Calendar Spread)
- **Backtest:** start/end date, underlying, **risk amount**, **start time**, **stop time**; form persists in `localStorage` (`moveStraddleBuyBacktestForm`). Calendar-style summary + equity curve + trade ledger (entry, SL, EMA, T1/T2 hits). Polls `GET /move-straddle/live` and WebSocket `move_straddle` while job runs.
- **Live / History:** disabled shell (live returns 501)

### API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/move-straddle/backtest` | Body: `startDate`, `endDate`, `underlying`, `riskAmount`, `startTime`, `stopTime`. |
| GET | `/move-straddle/live` | Stub status + `backtestJob` |
| GET | `/move-straddle/history` | `{ runs: [] }` until live ships |
| PATCH | `/move-straddle/live/config` | Accepts config (no engine) |
| POST | `/move-straddle/live/start` | **501** — not enabled |

WebSocket: `type: move_straddle`, `topic: move_straddle`.

**Backtest job result** (`backtestJob.result` when completed): `stats`, `trades`, `equityCurve`, `sessionDiagnostics`, `diagnosticSummary`, `exclusionReasons`, `params`. MV mark candles prefetched per session day from anchor through settlement.

---


## 11a. Strike Advisor (ML)

Standalone nav page that **trains** Gradient Boosting models on Delta **5m** spot candles (`BTCUSD` / `ETHUSD` via `CandleCacheService`), then forecasts:

1. **Primary:** probable **80% spot price range at 17:00 IST** on the sell-leg expiry day (`exit17PriceRange`: P10–P90 from residual bootstrap, display rounded to strike step; median P50 as headline `predictedSpotExit17`).
2. **Horizon band:** user-width price band over the next **X hours** (`rangeBand` / `rangeWidth`).
3. **Secondary:** nearest listed strike to range center (`suggestedStrike` / `suggestedMoneyness`); strike rankings demoted to Advanced UI.

### Training

- **Lookback:** `STRIKE_FORECAST_TRAIN_DAYS` (default **180**) × `STRIKE_FORECAST_HISTORY_STEPS` (default **4**) → **720 days** total 5m candles
- **Targets (`FEATURE_VERSION` 2):** log returns from origin spot to horizon / 17:00 exit labels; inference reconstructs with live spot
- **Samples:** 4-hour origin step on weekdays; up to **150,000** training rows (stratified cap)
- **Models (per underlying):** `GradientBoostingRegressor` for horizon and exit-17 log-return; holdout MAE/MAPE + recent 14-day exit-17 MAE stored
- **Uncertainty:** log-return residual bootstrap (`STRIKE_FORECAST_MC_PATHS`, default 5000) → `exit17Percentiles`, `exit17PriceRange`
- **Persistence:** MongoDB `strike_forecast_models` (`featureVersion`, `historyDepthDays`, `historySteps`, residuals)
- **Retrain:** when missing, `featureVersion` &lt; 2, or older than `STRIKE_FORECAST_RETRAIN_HOURS` (default 24)

### Frontend (`StrikeAdvisorPage`)

- Inputs: underlying, horizon hours (1–72), range width (50–2000, default **200**), sell expiry, include AI explanation
- Hero **17:00 probable range** + `Exit17RangeChart`; horizon band chart separate; MAPE beside MAE; low-confidence warning when holdout MAE &gt; 8% of spot
- Model status strip shows history depth, MAPE, recent 14d MAE; **Train model** async; polls every 3s while jobs pending

### Forecast response (completed job `result`)

| Field | Description |
|-------|-------------|
| `exit17PriceRange` | `{ low, high, center, confidenceLabel: "80%", coreLow, coreHigh, coreLabel: "50%" }` (display-rounded) |
| `exit17Percentiles` | `{ p10, p25, p50, p75, p90 }` full precision |
| `predictedSpotExit17` | P50 median (aligned with range) |
| `rangeBand` | Horizon band from `rangeWidth` |
| `suggestedStrike` | Nearest strike to `exit17PriceRange.center` |
| `strikeRankings` | Filtered MC rankings near median (Advanced) |
| `modelMeta` | `holdoutMaeExit17`, `holdoutMapeExit17`, `recentHoldoutMaeExit17`, `historyDepthDays`, `lowModelConfidence` |

### API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/strike-advisor/forecast` | Submit async forecast job (returns `{ status: "processing" }`; result via WebSocket) |
| GET | `/strike-advisor/model-status` | Train metadata + active `trainJob` / `forecastJob` (`?underlying=BTC` optional) |
| POST | `/strike-advisor/retrain` | Force async retrain |

---

## 12b. 1H SuperTrend Options Sell (ST Options)

**Full strategy reference:** [st-options-1h.md](./st-options-1h.md)

**Product:** Short PUT (Long) / short CALL (Short) on BTC or ETH using **1H** SuperTrend + EMA.

| Area | Detail |
|------|--------|
| Indicators | TV-parity EMA(close, N) SMA-seed; SuperTrend(HL2, period, mult) RMA ATR + Pine pinning; **120d** warmup (`utils/st_options_indicators.py`) |
| Defaults | ST(10, 3), EMA(10), min premium **5%** of perp, SL **105% premium rise**, TP **95% premium melt**, **breakevenDecayPct 40** (0 = off), **maxRisk 100**, **maxStDistancePct 0.3** (0 = off), live **pairHedgeDecayPct 0** (0 = off) |
| Entry | Long: close &gt; ST sentiment, close &lt; EMA and still &gt; ST → sell PUT. Short mirrors → sell CALL. **Live:** limit sell at mark/last − $1; lots from that limit + configured SL % **widened 40% for stop-market slippage** + maxRisk (skip if 1 lot &gt; maxRisk). Unhedged live MTM ≤ −maxRisk flattens (`max_loss`) even with broker SL attached. Broker SL/TP stay **stop-market** (trigger only). **Live + backtest:** **maxStDistancePct** (default **0.3**, 0 = off) requires `|close−ST|/close×100` &lt; threshold. **Backtest:** lots from resolved premium (no slippage buffer) |
| Waterfall | **Live:** Eligible T0 (≤10:30 IST) + T1; **ATM±1** only (OTM1 / ATM / ITM1); keep strikes whose ticker **volume &gt; band average** (missing/zero count in the average; skip if none); furthest OTM wins, ties → T1; min premium % floor. **Backtest `min_pct`:** OTM3→ATM→ITM3 (no volume gate). **Backtest-only modes:** `fixed` (moneyness + auto expiry &lt;05:30→T0 else T1), `supertrend` (ATM on ST line), `min_abs` (absolute premium floor, depth 10) |
| Exits | Configurable SL/TP premium brackets (defaults **2.05×** / 0.05×); opposite ST close; optional move-SL-to-BE after `breakevenDecayPct` melt; **17:15 IST** same-day square-off; settle after **17:30**; Force close for missing contracts; with live hedge open, main exit closes both; combined pair MTM **or unhedged main** ≤ −maxRisk → `max_loss` |
| Live control | Limit entry persisted as `pending_entry` immediately; fill confirmed via order poll + **retry cancel** (order id + cancel-all) until gone/filled + fills API + multi-try short-position check, then promoted to open with broker SL + TP; leftover **working limits are cancelled** on reconcile (404 is not “keep watching”); unfilled pending clears after ~3 ticks without the 150s min-age while the order was still open; each tick also **adopts naked shorts** on the live underlying (no matching open/pending trade) and retries missing brackets (**links existing Delta SL/TP** if already present); reconciles **broker-flat** shorts (Delta closed outside ST → History with fill-based PnL); BE trail amends broker SL when triggered; pending brackets cancelled before ST-flip/manual/expiry exits; soft mark/last fallback if attach fails; optional **pair hedge** via `pairHedgeDecayPct` (hot-toggle while running) with **fixed hedge SL** at open (`hedgeEntry + (mainProfit$ + maxRisk)/(cv×lots)`) + broker SL-only; order rejects surface Delta codes (e.g. insufficient margin + balances) in Updates |
| Backtest | Parallel product/candle prefetch; strike modes + optional **oneTradePerFormation** + **skipSetupsAfterTarget** + **maxStDistancePct** + optional **pair hedge** (same-strike opposite; immediate or on_decay); **maxRisk** lot sizing from configured SL %; dynamic sizing as **% of base risk**; persisted settings/runs; richer summary; compare + PDF |
| Concurrency | One open Long **and** one open Short |
| UI | Live gear (**Max risk $**, SL/TP/BE, **Max close→ST distance %**, **Hedge after decay %** editable while on); Running cards full-width with Bias (live ST / trade colour), Open (est.) + Est. loss (stop) + Est. profit (target), main \| hedge side-by-side and hedge Protect at when hedged; Updates panel fills remaining viewport height with footer pinned (app shell `h-dvh`, main scrolls); History pages of 20 with **Load more** + capped table scroll (client window fallback if API is not cursor-paged); Backtest: From/To outside + gear (max risk, strike mode / formation / skip-after-Target / max close→ST distance % / dyn % sizing / pair hedge), saved runs picker (selection sticks while browsing; WS does not force latest), Compare modal; Advanced confirm; **Quantity** (lots) on Running / History / Backtest / Dashboard Recent Trades; streak KPIs as `4(2)` |
| Code | `services/st_options_service.py`, `routers/st_options.py`, `utils/st_options_backtest.py`, `utils/st_options_pair_hedge.py`, `utils/st_options_resolver.py` |

### API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/st-options/meta` | Defaults, underlyings, fixed rules |
| GET/PATCH | `/st-options/config` | Live settings, including `maxRisk` / `stopLossPct` / `takeProfitPct` / `breakevenDecayPct` / `maxStDistancePct` / `pairHedgeDecayPct` (0 = hedge off) |
| POST | `/st-options/start` \| `/stop` | Start (optional settings body incl. maxRisk + SL/TP/BE/hedge %) / Stop (cancel brackets, flatten opens + hedges, then disable; may return `closeFailures`) |
| POST | `/st-options/trades/{id}/force-close` | Mark open trade closed in DB without broker reduce |
| GET | `/st-options/live` | Config, active trades, indicator, `status` (dual activity), backtestJob |
| GET | `/st-options/history` | Closed live trades; `limit` (default 20, max 100) + optional `cursor`; returns `{ trades, nextCursor, hasMore, summary }` (`summary` = all closed trades) |
| GET/PATCH | `/st-options/backtest/config` | Per-user backtest settings (separate from live), incl. `maxRisk`, dyn % knobs + `strikeSelectMode` / `strikeType` / `minPremiumAbs` / `oneTradePerFormation` / `skipSetupsAfterTarget` / `maxStDistancePct` / `pairHedgeEnabled` / `pairHedgeMode` / `pairHedgeDecayPct` |
| GET | `/st-options/backtest/runs` | Saved backtest runs (last ~50) |
| GET/DELETE | `/st-options/backtest/runs/{id}` | Load or delete a saved run (full result on GET) |
| POST | `/st-options/backtest` | Async job `{ from, to, …settings, strikeSelectMode?, … }` → persists run on complete; job may include `runId` |
| GET | `/st-options/backtest/job` | Latest job status |

**WebSocket:** `type: st_options_session` (`topic: st_options`) — includes `status` engine snapshot; `backtestJob` may include `runId` when saved.

**Mongo:** `st_options_config`, `st_options_trades`, `st_options_backtest_config`, `st_options_backtest_runs`.

---

## 12. REST API reference

All routes under `/api` unless noted. Auth required except health.

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create user |
| POST | `/auth/login` | Login |
| POST | `/auth/logout` | Revoke current session |
| POST | `/auth/logout-all` | Revoke other sessions |
| GET | `/auth/me` | Current user |

### Accounts

| Method | Path | Description |
|--------|------|-------------|
| GET | `/accounts` | List accounts |
| POST | `/accounts` | Add Delta account (`exchange`: delta) |
| DELETE | `/accounts/{id}` | Remove account |
| POST | `/accounts/{id}/select` | Set active account |

### Execution (spot SL engine)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/execution/options/search?q=` | Search live BTC/ETH options (strike ascending) |
| POST | `/execution/preview` | Margin preview for sell `{ symbol, quantityLots }` |
| POST | `/execution/trade` | Arm monitor → `Pending Trigger` |
| GET | `/execution/monitors` | List monitors |
| POST | `/execution/monitors/{id}/cancel` | Cancel pending/placed monitor |

### ST Options (1H SuperTrend sell)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/st-options/meta` | Defaults + fixed rules |
| GET | `/st-options/config` | Live settings, including SL/TP / BE / pairHedgeDecayPct |
| PATCH | `/st-options/config` | Update settings (`stopLossPct` / `takeProfitPct` / `breakevenDecayPct` / `pairHedgeDecayPct` included) |
| POST | `/st-options/start` | Start live engine (optional settings incl. SL/TP/hedge % in body) |
| POST | `/st-options/stop` | Cancel broker brackets, flatten opens (+ hedges), then stop; may return `closeFailures` |
| POST | `/st-options/trades/{id}/force-close` | DB-only close when contract missing |
| GET | `/st-options/live` | Snapshot (active, indicator, backtestJob) |
| GET | `/st-options/history` | Closed live trades; `limit` (default 20, max 100) + optional `cursor`; returns `{ trades, nextCursor, hasMore, summary }` (`summary` = all closed trades) |
| GET/PATCH | `/st-options/backtest/config` | Per-user backtest settings (separate from live; dynamic sizing + strike modes) |
| GET | `/st-options/backtest/runs` | List saved runs (~50) |
| GET/DELETE | `/st-options/backtest/runs/{id}` | Load / delete saved run |
| POST | `/st-options/backtest` | Start async backtest (persists run; optional dynamic sizing / strike modes / formation gate) |
| GET | `/st-options/backtest/job` | Latest backtest job (`runId` when saved) |

### Orders

| Method | Path | Description |
|--------|------|-------------|
| POST | `/orders` | Place order (Delta) |
| GET | `/orders/active` | Open orders |
| POST | `/orders/{id}/cancel` | Cancel order |

### Live

| Method | Path | Description |
|--------|------|-------------|
| GET | `/live/prices` | Price snapshot |
| GET | `/market/near-ath?thresholdPct=5` | Perp coins ranked by % below all-time high (weekly-candle ATH, cached) |
| GET | `/market/movers?limit=20&fundingWindowHours=8` | Top 24h gainers with funding rate + recent funding-rate change |
| GET | `/market/highest-funding?limit=30` | Perpetuals ranked by funding normalized to per-8h (highest first) |

### Positions (unified)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/positions/open` | Open positions + open orders across all connected accounts |
| GET | `/positions/history?broker=all\|delta` | Past orders grouped by broker |

### Arbitrage

| Method | Path | Description |
|--------|------|-------------|
| GET | `/arbitrage/funding` | Current funding comparison snapshot |
| GET | `/arbitrage/meta` | Exchanges, normalization basis, Delta funding source (websocket) |
| GET | `/arbitrage/opportunities` | BCH/ETC negative-funding opportunities |
| POST | `/arbitrage/opportunities/quote` | Quote opportunity legs + margin + cashflow/fees/liquidation/alignment |
| POST | `/arbitrage/opportunities/execute` | Execute long alt + short hedge |
| GET | `/arbitrage/opportunities/history` | Executed opportunity trade history |
| POST | `/arbitrage/opportunities/close` | Close both legs of an open opportunity |
| GET | `/arbitrage/spread/status` | Spread execution status + open positions |
| PATCH | `/arbitrage/spread/config` | Update spread execution config |
| POST | `/arbitrage/spread/auto` | Toggle Auto Execute |
| POST | `/arbitrage/spread/execute` | Manual spread open for a coin |
| POST | `/arbitrage/spread/close` | Close a spread position |

### Directional options

| Method | Path | Description |
|--------|------|-------------|
| POST | `/directional-options/backtest` | Async BB FSM backtest on aggregated 90m bars |
| GET | `/directional-options/live` | Setups, active legs, `backtestJob` |
| GET | `/directional-options/history` | Live trade history |
| GET/PUT | `/directional-options/backtest/config` | Saved backtest form |
| POST | `/directional-options/start` | Start 90m BB FSM scanner (`symbol`, `bb_length`, `bb_mult`) |
| POST | `/directional-options/stop` | Stop scanner; optional `closePositions` |
| GET | `/directional-options/active` | Alias of live payload |

### Move Fade Writer

| Method | Path | Description |
|--------|------|-------------|
| POST | `/move-fade/move-study` | BTC move study from 6:30 PM IST anchor (separate up/down %) |
| POST | `/move-fade/backtest` | Strike-ladder backtest ITM10…OTM10 with SL/TP/re-entry rules |



### Strike advisor

| Method | Path | Description |
|--------|------|-------------|
| POST | `/strike-advisor/forecast` | ML strike forecast job (async; result on WebSocket) |
| GET | `/strike-advisor/model-status` | Trained model metadata per underlying |
| POST | `/strike-advisor/retrain` | Force model retrain |

### Meta

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/meta/public-ip` | Server outbound IP for Delta API whitelisting |

### WebSocket

| Path | Description |
|------|-------------|
| `/ws/live?token=` | Live feed (see §13) |

---

## 13. WebSocket protocol

Connect: `ws://<host>/ws/live?token=<bearer>`

Client reconnects with exponential backoff on unexpected closes only (not logout/cleanup/auth `1008`). Client `{ "type": "ping" }` every 20s; server `{ "type": "pong" }` refreshes transport liveness. Multiple tabs per token remain allowed.

### Server → client messages

| `type` / `topic` | Description |
|------------------|-------------|
| `snapshot` | Initial bootstrap: accounts, prices, orders |
| `price` | Single-symbol price tick (event-driven from Delta public WS via `LivePriceBroadcaster`; no server-side poll loop) |
| `margin` | Account margin update |
| `arbitrage_funding` | Funding-rate comparison table |
| `spread_execution` | Spread config, auto running flag, open spread positions, fund inflow totals |
| `positions` | Unified open positions + open orders across all accounts (broker + app) |
| `execution_monitor` (`topic: execution`) | Spot SL monitor list / updates (`monitors`, status, safe mode) |
| `st_options_session` (`topic: st_options`) | ST Options config, `active[]`, indicator, `status` (dual activity), `backtestJob` |
| `pong` | Reply to client `ping` |

Client may send `{ "type": "ping" }`.

---

## 14. Data model (MongoDB)

| Collection | Purpose |
|------------|---------|
| `app_users` | Users (email, password hash, display name) |
| `app_sessions` | Bearer sessions |
| `delta_accounts` | Exchange accounts (`exchange`, encrypted secrets) |
| `spread_exec_config` | Per-user spread execution settings |
| `spread_trades` | Persisted spread trades (auto/manual) |
| `opportunity_trades` | Manual opportunity executions (long alt + short hedge); `accountId` stored for manual close |
| `directional_options_setups` | Per-user BB FSM scanner configs |
| `directional_options_trades` | Live directional short option legs |
| `candle_cache` | **Exchange-scoped** historical candles `{ exchange, symbol, resolution, time, open, high, low, close, volume }` — keyed by exchange (e.g. `delta`), shared across all accounts; unique on `(exchange, symbol, resolution, time)` |
| `candle_cache_coverage` | Fetched time-range coverage per `(exchange, symbol, resolution)` so backtests only fetch uncovered gaps |
| `strike_forecast_models` | Per-underlying trained strike advisor models (pickled sklearn regressors, holdout residuals, MAE, `trainedAt`) |
| `st_options_config` | Per-user 1H ST Options settings + `enabled`, including `maxRisk` / `stopLossPct` / `takeProfitPct` / `breakevenDecayPct` / `maxStDistancePct` |
| `st_options_trades` | Open + closed ST Options live trades; captures per-entry SL/TP %, computed premiums, `bracketAttached`, `stopOrderId`, `takeProfitOrderId`, entry/close order IDs, PnL, and optional pair-hedge fields (`pairId`, `legRole`, `hedgeStatus`, `hedgeSymbol`, `hedgeStopPremium`, `hedgeStopOrderId`, …); `pending_entry` while limit fill/protection is confirmed |
| `st_options_backtest_config` | Per-user backtest settings (separate from live), including `maxRisk`, dyn % sizing + strike-select modes + formation gate + `maxStDistancePct` |
| `st_options_backtest_runs` | Saved backtest results (`settings`, `summary`, `trades`, `diagnostics`); keep last ~50 per user |

---

## 15. Background jobs

| Service | Interval | Description |
|---------|----------|-------------|
| `DeltaMarketDataService` | WebSocket | Delta public price stream + BTCUSD `candlestick_1h` closed bars; JSON heartbeat (`ping_interval=None`) |
| `DeltaPrivateStreamService` | WebSocket | Margin + positions + orders updates for all connected Delta accounts on live clients; JSON heartbeat + reconnect backoff |
| `DeltaRestClient` | Per request | HMAC signing at httpx send-time; one retry on `expired_signature` |
| `PositionsService` | WS ticks + 15s MTM | Subscribes open position symbols to public marks; rebroadcasts `type: positions` on each relevant tick; MTM REST refresh skipped when private WS is healthy (<30s since last refresh) |
| `ArbitrageService` | 15s poll | Funding-rate snapshot + broadcast |
| `SpreadExecutionService` | 10s poll (per Auto Execute user) | Spread auto loop, metrics refresh, liquidation guard |
| `DirectionalOptionsService` | WS candles + premiums | Supertrend signal + simulated option flips (per enabled user) |
| `CalendarSpreadService` | ~30s deploy + ~15s MTM | Daily calendar spread forward-test or live orders (per enabled user) |
| `StOptionsService` | ~15s poll | 1H ST Options live entries/exits + premium monitors; async backtest jobs |

---

## 16. Configuration

Key environment variables (see `config.py`):

| Variable | Description |
|----------|-------------|
| `MONGODB_URI` | MongoDB connection |
| `CRYPTOBRIDGE_ENCRYPTION_KEY` | Fernet key for API secrets |
| `DELTA_API_BASE_URL` | Delta REST base (default India) |
| `CORS_ORIGINS` | Allowed frontend origins |
| `SERVER_PUBLIC_IP` | Optional override for the server outbound IP shown for Delta whitelisting; auto-detected if unset |
| `LOG_LEVEL` | App log level (default `INFO`); applied at startup. Set `DEBUG` for verbose tracing. Spread execution logs each step (`[spread]`) and Delta REST calls log request/response (`[delta]`) — keys/signatures are never logged |
| `LOG_TO_FILE` | When `true` (default), write logs to a rotating local file only (no stdout). Set `false` for console-only output (e.g. quick local debugging) |
| `LOG_DIR` | Directory for log files (default `{repo_root}/logs`; gitignored, created at startup) |
| `LOG_FILE` | Rotating log filename inside `LOG_DIR` (default `cryptobridge.log`) |
| `LOG_MAX_BYTES` | Rotate when the active log file exceeds this size in bytes (default `10485760` = 10 MB) |
| `LOG_BACKUP_COUNT` | Number of rotated backup files kept (default `5`, e.g. `cryptobridge.log.1` … `.5`) |
| `LOG_FORMAT` | `text` (default, human-readable) or `json` (one JSON object per line) |

---

## 17. Frontend structure

**Light/dark theme** via Tailwind `darkMode: "class"`. `ThemeProvider` (`utils/theme/ThemeContext.jsx`) reads/writes `localStorage` key `cryptobridge.theme` (default **dark**). **Theme switcher** in `WorkspaceHeader` (sun/moon button) toggles `html.dark`. Shared tokens in `utils/workspace/workspaceClasses.js` use `light` + `dark:` variants (`card`, `field`, `chartSurface`, `modalPanel`, `textHeading`, `textBody`, `textMuted`, etc.). Surface helpers (`card`, `cardInner`, `navShell`, `pageShell`) set default readable text in both themes.

Workspace shell (`appShell()`): light `slate-50` or dark `zinc-950` body; header adapts (`headerShell()`). `App.jsx` is auth + WebSocket + routing only (~370 lines); page markup lives in child components.

```
frontend-react/src/
  App.jsx                          # Auth gate, WS lifecycle, currentPage, toast
  main.jsx                         # ThemeProvider + apply stored theme on load
  index.css                        # Light/dark html + body backgrounds
  api.js
  utils/
    theme/
      themeStorage.js              # cryptobridge.theme read/write, applyThemeClass
      ThemeContext.jsx             # useTheme(), toggleTheme()
      chartTheme.js                # useChartTheme() SVG stroke/fill tokens for light/dark
    liveMerge.js
    workspace/
      workspaceClasses.js          # card, field, subTab, appShell, chartSurface, theme tokens
      workspaceFormatters.js       # USD, spot tick direction, PnL colors
      workspaceNav.js              # Nav item defs + badge counts
  components/
    workspace/                     # App chrome (one file per component)
      CryptoBridgeLogo.jsx         # SVG logo + optional wordmark (CRYPTOBRIDGE_LOGO_SRC)
      icons.jsx
      ThemeSwitcher.jsx            # Light/dark toggle in header
      WorkspaceToast.jsx
      WorkspaceHeader.jsx
      WorkspaceNav.jsx
      WorkspaceFooter.jsx
      WorkspaceSettingsModal.jsx
      AuthPanel.jsx
      settings/
        SettingsAccountsTab.jsx
        SettingsIpWhitelistTab.jsx
    ui/                            # Reusable themed primitives (light + dark)
      WorkspaceCard.jsx
      WorkspaceSubTabs.jsx
      WorkspaceKpiCard.jsx
      WorkspaceDataTable.jsx
      WorkspaceProgressBar.jsx
      WorkspaceConfirmDialog.jsx
      WorkspaceField.jsx
    dashboard/
      DashboardPage.jsx            # Thin orchestrator
      DashboardKpiGrid.jsx
      DashboardEquityChart.jsx
      DashboardRecentTrades.jsx
      DashboardAccountsList.jsx
      DashboardPositionsPreview.jsx
      dashboardUtils.js
    st-options/
      StOptionsPage.jsx            # Live Running/History + Backtest
      StOptionsTradeTable.jsx      # Summary KPIs + trade ledger
    positions/
      ActivePositionsPage.jsx
      PositionsSubTabs.jsx
      PositionsKpiRow.jsx
      PositionsOpenLedger.jsx
      PositionsOpenOrdersTable.jsx
      PositionsPastOrdersTable.jsx
      PositionsPayoffTab.jsx
      positionsUtils.js
      positionsWorkspaceUtils.js
    sps/
      SpsPage.jsx
      SpsStartModal.jsx
      SpsBacktestModal.jsx
      SpsBacktestResults.jsx
      SpsSessionStatus.jsx
    movestraddle/
      MoveStraddlePage.jsx
      MoveStraddlePageHeader.jsx
      MoveStraddleLiveStub.jsx
    strike-advisor/
      StrikeAdvisorPage.jsx
      StrikeAdvisorRangeChart.jsx
```

**Nav pages:** `dashboard`, `positions`, `rwb`, `sps`, `move-straddle`, `strike-advisor`

**Removed (workspace rebuild):** `Header.jsx`, `Footer.jsx`, `ManageAccountModal.jsx`, `CalendarLiveSettingsModal.jsx`

---

## 18. Tests

Backend (`backend-python/tests/`):

- Auth, signing, crypto, wallet margin, order economics, risk limits
- `test_arbitrage_service.py` — coin matching, normalization
- `test_arbitrage_runner_helpers.py` — sizing, direction/price, liquidation buffer, replacement hysteresis
- `test_spread_execution_helpers.py` — capped leverage, margin from balances, auto spread pick
- `test_sps_indicators.py` — EMA20, RMA, SuperTrend HL2, ETH golden-bar TV parity, drift log
- `test_sps_engine.py` — armed pullback entry, EMA/ST blend clearance, signal direction
- `test_sps_option_resolver.py` — maturity steps, listed ladder waterfall
- `test_options_trade_helpers.py` — short-option PnL, lots, contract value
- `test_st_options_indicators.py` — EMA SMA-seed, RMA, SuperTrend TV parity
- `test_st_options_resolver.py` — T0/T1 waterfall, ATM±1 volume gate, premium brackets, entry helpers

Run: `cd backend-python && pytest`

Frontend build: `cd frontend-react && npm run build`

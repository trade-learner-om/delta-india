# CryptoBridge Backend — Full Functionality Brief (UI Planning)

**Purpose:** Copy-paste reference for UI design tools (e.g. Gemini Canvas).  
**Branch:** `arbitrage`  
**Backend entry:** `backend-python/cryptobridge/main.py`  
**Last updated:** 2026-07-04

This document reflects what is **actually wired** in the current backend, with feature maturity called out explicitly.

---

## 1. Product summary

**CryptoBridge** is a Delta Exchange India trading workspace.

- **Exchange:** Delta India only (`api.india.delta.exchange`, public + private WebSockets)
- **Auth:** Local email/password; Bearer session tokens (7-day TTL, up to 6 concurrent sessions)
- **Accounts:** Multiple Delta API accounts per user; secrets encrypted at rest
- **Real-time:** Single WebSocket feed `/ws/live` pushes prices, margin, positions, and strategy state
- **Focus areas:** Options strategies (calendar spread, short strangle backtest), ML strike advisor, unified positions view, portfolio dashboard

**Current frontend nav pages:**

| Page ID | Label |
|---------|-------|
| `dashboard` | Dashboard |
| `positions` | Active Positions |
| `calendar-spread` | Calendar Spread |
| `move-straddle` | Daily Strangle |
| `strike-advisor` | Strike Advisor |

---

## 2. Stack & architecture

| Layer | Technology |
|-------|------------|
| API | FastAPI, Python 3.9+, uvicorn :8080 |
| DB | MongoDB (Motor async) |
| Exchange | httpx REST + websockets to Delta |
| Live feed | `/ws/live?token=<bearer>` |
| Logs | Rotating file `logs/cryptobridge.log` (default; no stdout) |

### Core backend services (started at app boot)

| Service | Role |
|---------|------|
| `DeltaRestClient` | Signed Delta REST (orders, positions, candles, profile, wallet) |
| `DeltaMarketDataService` | Delta public WS — tickers, marks, funding, option premiums |
| `DeltaPrivateStreamService` | Per-account private WS — margin, positions, orders |
| `SnapshotService` | Initial WS bootstrap (accounts, prices, orders, running P/L) |
| `PositionsService` | Unified open positions + orders across all accounts; live MTM |
| `CalendarSpreadService` | Calendar spread backtest + **live engine** (forward test or real orders) |
| `MoveStraddleService` | Daily short strangle **backtest only** (live = stub) |
| `StrikeForecastService` | ML strike/range forecasting (async jobs) |
| `CandleCacheService` | Shared historical candle cache for backtests/ML |
| `AccountService` / `AuthService` / `OrderService` | CRUD + trading primitives |

---

## 3. Authentication

| Action | Method | Path | Notes |
|--------|--------|------|-------|
| Register | POST | `/api/auth/register` | `displayName`, `email`, `password` (≥8 chars) → `{ token }` |
| Login | POST | `/api/auth/login` | → `{ token }` |
| Logout | POST | `/api/auth/logout` | Revokes current session |
| Logout all | POST | `/api/auth/logout-all` | Revokes other sessions |
| Me | GET | `/api/auth/me` | `displayName`, `email`, `selectedAccountId` |

**UI needs:** Login/register screens, session persistence (`localStorage` token), auth-gated app shell, logout in avatar menu.

---

## 4. Accounts & wallet

| Action | Method | Path |
|--------|--------|------|
| List accounts | GET | `/api/accounts` |
| Add account | POST | `/api/accounts` |
| Select active | POST | `/api/accounts/select` |
| Delete | DELETE | `/api/accounts/{id}` |
| Update risk | PATCH | `/api/accounts/{id}/risk` |

**Add account body:** `accountName`, `apiKey`, `apiSecret`, `exchange: "delta"`

**On add:** Backend validates credentials via Delta `GET /v2/profile`, encrypts secret, fetches wallet margin.

**Account object (API response):** `id`, `accountName`, `exchange`, `exchangeUserId`, `availableMargin`, `balance`, `netEquity`, `currencyCode`, `selected`, `walletError`

**UI needs:**

- Account Settings modal (add/delete/select accounts)
- Server public IP hint for Delta whitelist: `GET /api/meta/public-ip`
- Account selector in header
- Risk amount per account (optional field)

---

## 5. Live market data & WebSocket hub

### REST

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/live/prices` | `{ prices, market_status, socket_connected, subscribed_symbols }` |
| GET | `/api/health` | `{ status, service, marketFeedStatus, mongoStatus, timestamp }` |
| GET | `/api/meta/public-ip` | `{ ip }` for Delta API whitelist |

### WebSocket `/ws/live?token=`

**On connect, server sends (in order):**

1. `snapshot` — accounts, prices, orders, running P/L, market feed status
2. `positions` — open positions + open orders (all accounts)
3. `calendar_spread` — calendar spread live state
4. `move_straddle` — strangle status (backtest job only)
5. `strike_forecast` — strike advisor job status

**Ongoing server → client message types:**

| `type` | `topic` | Purpose |
|--------|---------|---------|
| `snapshot` | — | Bootstrap (once) |
| `price` | `price` | Per-symbol tick (`symbol`, `tick`: price, mark, bid, ask, change24h) |
| `margin` | `margin` | Account margin/balance update |
| `positions` | `positions` | Open positions + open orders + totals |
| `calendar_spread` | `calendar` | Calendar spread config, open runs, payoff, legs |
| `move_straddle` | `move_straddle` | Strangle backtest job progress |
| `strike_forecast` | `strike_forecast` | Forecast/train job progress |
| `pong` | `system` | Reply to client `{ type: "ping" }` |

**Client → server:** `{ "type": "ping" }`

**UI needs:**

- Global live connection indicator (header dot)
- BTC/ETH spot chips from `price` ticks
- Tab title running P/L from open positions
- All strategy pages merge REST initial load + WS live updates

---

## 6. Active Positions (unified broker view)

| Method | Path |
|--------|------|
| GET | `/api/positions/open` |
| GET | `/api/positions/history?broker=all\|delta` |

**WS:** `type: positions` (also sent on connect)

**Open payload shape:**

```json
{
  "type": "positions",
  "openPositions": [],
  "openOrders": [],
  "openCount": 3,
  "openOrderCount": 1,
  "totalRunningPnl": 123.45,
  "totalNotional": 50000,
  "updatedAt": "..."
}
```

**Each position includes:** `accountId`, `symbol`, `side`, `size`, `entryPrice`, `markPrice`, `runningPnl`, `productType` (perp/option), `source: "broker"`

**Updates:** Private WS + public mark ticks (options MTM recomputed) + 15s REST fallback

**UI needs:**

- **Open** tab: position cards + open orders table
- **Past Orders** tab: history grouped by broker
- **Payoff** chart for selected legs (calendar pairs auto-detected)
- Multi-account aggregation
- Link to Calendar Spread when legs belong to a strategy run

---

## 7. Calendar Spread (flagship — backtest + live)

**Maturity:** Backtest ✅ · Live engine ✅ · Real orders ✅ · History ✅

### Strategy concept (for UI copy)

Daily options calendar: **sell near expiry + buy same strike farther expiry** (CE or PE chosen by max profit). Deploy at configured IST time; exit on stop, target, or sell-leg expiry square-off.

**Modes:**

- `forward_test` — simulated premiums, no broker orders
- `live_order` — real Delta market orders on arbitrage-selected account

### REST API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/calendar-spread/backtest` | Run historical backtest (async job) |
| GET | `/api/calendar-spread/backtest/config` | Load saved backtest form |
| PUT | `/api/calendar-spread/backtest/config` | Save backtest form |
| GET | `/api/calendar-spread/live` | Live status snapshot |
| PATCH | `/api/calendar-spread/live/config` | Update live settings |
| POST | `/api/calendar-spread/live/start` | Start engine |
| POST | `/api/calendar-spread/live/stop` | Stop engine; body `{ exitPositions: bool }` |
| GET | `/api/calendar-spread/history` | All runs (open + closed) |

### Backtest inputs (form fields)

| Field | Default | UI control |
|-------|---------|------------|
| `underlying` | BTC | BTC / ETH toggle |
| `deployTime` | 20:00 IST | Time picker (17:30–18:30 blocked) |
| `exitTime` | 17:00 IST | Time picker |
| `sellMoneyness` | ATM | ITM10…OTM10 dropdown |
| `ivFilterEnabled` | false | Toggle + `targetIv` |
| `sellExpiry` / `buyExpiry` | next_day / weekly | Expiry selectors (must differ) |
| `quantity` + `quantityUnit` | 0.5 BTC | Number + lots/BTC/ETH |
| `stopLossValue` / `stopLossMode` | 50% | Points or % of max loss |
| `stopLossCapMode` | capped | capped vs configured_only |
| `takeProfitValue` / `takeProfitMode` | 70% | Points or % of max profit; 0 = off |
| `startDate` / `endDate` | last 7 days | Date range |
| Dynamic quantity | off | N losses → increase; M profits → decrease; max cap |

### Live settings (additional)

| Field | Default | Notes |
|-------|---------|-------|
| `mode` | forward_test | forward_test / live_order |
| `enabled` | false | Engine on/off |
| `deployCatchUp` | immediate | immediate vs next_slot when starting late |
| `lots` | 1 | 1 lot = 0.001 BTC / 0.01 ETH |
| Dynamic sizing | off | Mid-trade scale-up/down on open runs |

### WS payload `calendar_spread`

```json
{
  "type": "calendar_spread",
  "config": {},
  "running": true,
  "openPosition": {},
  "openPositions": [],
  "openPositionBundles": [
    { "position": {}, "legs": [], "payoff": {} }
  ],
  "openPositionsSummary": { "count": 2, "totalRunningPnl": 150.2 },
  "legs": [],
  "payoff": {},
  "payoffStatus": "ready",
  "nextDeployTs": 1710000000,
  "spot": 95000,
  "trades": [],
  "backtestJob": {},
  "updatedAt": "..."
}
```

### History run detail (per collapsible panel)

`deployedAt`, `closedAt`, `exitReason`, `mode`, `strikeLabel`, `quantity`, `lots`, `sellEntry`, `buyEntry`, `sellExit`, `buyExit`, `netDebit`, `runningPnl`, `realizedPnl`, `maxProfit`, `maxLoss`, `targetPnl`, `stopPnl`, `sellSymbol`, `buySymbol`, `orderIds`, `dynamicQuantityScaling[]`

### UI pages to plan

1. **Backtest tab** — full config form, Run button, summary stats, equity curve, paginated trade table
2. **Live tab** — Start/Stop, settings modal, spread-set tabs when multiple open, summary grid, payoff chart, legs table, dynamic sizing indicator + tooltip link
3. **History tab** — performance equity + daily PnL grid, collapsible run panels, live PnL merge from WS

**Stop confirmation:** checkbox “Exit all running positions” when stopping with open trades.

---

## 8. Daily Short Strangle (Move Straddle)

**Maturity:** Backtest ✅ · Live ❌ (501) · History ❌ (empty)

### Strategy concept

0DTE short strangle: deploy **07:00 IST**, sell call + put at moneyness/premium filters, per-leg stop-loss, square-off **17:00 IST**.

### REST API

| Method | Path | Status |
|--------|------|--------|
| POST | `/api/move-straddle/backtest` | Async job |
| GET | `/api/move-straddle/live` | Stub config + `backtestJob` |
| GET | `/api/move-straddle/history` | `{ runs: [] }` |
| PATCH | `/api/move-straddle/live/config` | Accepts but no engine |
| POST | `/api/move-straddle/live/start` | **501** |
| POST | `/api/move-straddle/live/stop` | **501** |

### Backtest inputs

`startDate`, `endDate`, `underlying`, `deployTime`, `strikeSelection` (moneyness/premium/range), `moneyness` (ITM_10…OTM_10), `minPremium`, `maxPremium`, `rangeMinPremium`, `rangeMaxPremium`, `quantity`, `quantityUnit`, `stopLossMode`, `stopLossValue`

### Backtest result stats

`winBothLegs`, `winOneLeg`, `loseBothLegs`, equity curve, per-trade leg PnL, `legOutcome`

### UI to plan

- **Backtest tab** — same chrome as Calendar Spread; poll/WS `backtestJob`
- **Live / History tabs** — disabled shells or “coming soon” until backend ships

---

## 9. Strike Advisor (ML)

**Maturity:** Train + forecast ✅ · Apply to Calendar Spread ✅

### Purpose

Train Gradient Boosting models on Delta 5m BTC/ETH candles; forecast:

1. **80% spot range at 17:00 IST** on sell-leg expiry day (`exit17PriceRange`)
2. **Horizon price band** over next X hours
3. **Suggested strike/moneyness** for Calendar Spread

### REST API

| Method | Path |
|--------|------|
| POST | `/api/strike-advisor/forecast` |
| GET | `/api/strike-advisor/model-status?underlying=BTC` |
| POST | `/api/strike-advisor/retrain` |

### Forecast request

`underlying`, `horizonHours` (1–72), `rangeWidth` (50–2000), `sellExpiry`, `includeExplanation` (optional LLM text)

### Forecast result (completed job)

`exit17PriceRange` (low/high/center, 80% band), `exit17Percentiles` (p10–p90), `predictedSpotExit17`, `rangeBand`, `suggestedStrike`, `suggestedMoneyness`, `strikeRankings`, `modelMeta` (MAE, MAPE, low confidence flag), optional `explanation`

### WS `strike_forecast`

`forecastJob` and `trainJob` with `status`: `processing` | `completed` | `failed`

### UI to plan

- Input panel (underlying, horizon, range width, sell expiry)
- Hero 17:00 range chart + horizon band chart
- Model status strip (history depth, MAE/MAPE, last trained)
- **Train model** + **Run forecast** buttons with 3s polling while processing
- **Apply to Calendar Spread** → PATCH live config `sellMoneyness`
- Low-confidence warning when holdout MAE > 8% of spot

---

## 10. Orders API (integrator — no dedicated UI today)

| Method | Path |
|--------|------|
| POST | `/api/orders` |
| GET | `/api/orders/active` |
| POST | `/api/orders/{id}/cancel` |

**Place order body:** `symbol`, `side`, `orderType` (LIMIT/MARKET), `size`, `entry`, optional `stopLoss`, `target`

Uses **selected** Delta account. Manual trading ticket UI was removed; endpoints remain for automation.

---

## 11. Dashboard (frontend-built from WS data)

**No dedicated `/api/dashboard` in current backend.**

Dashboard is composed from:

- WS `snapshot` → accounts, balances, running P/L
- WS `positions` → open position stats, allocation donut
- Client-side aggregation in `DashboardPage`

**Widgets to plan:**

- Estimated balance (all accounts vs selected)
- Open position count
- Running P/L
- Portfolio performance chart
- Asset allocation donut
- Trade history table
- Date range filters (1D / 1W / 1M / 1Y / All)

> **Note:** [FEATURES.md](./FEATURES.md) describes a richer dashboard tied to `spread_trades` arbitrage execution. That arbitrage/spread-execution backend is **not mounted** in current `main.py`.

---

## 12. MongoDB collections

| Collection | UI-relevant content |
|------------|---------------------|
| `app_users` | Profile |
| `app_sessions` | Auth sessions |
| `delta_accounts` | Connected exchanges |
| `calendar_spread_config` | Live settings + dynamic qty state |
| `calendar_spread_backtest_config` | Saved backtest form |
| `calendar_spread_trades` | Live/history runs |
| `candle_cache` | Backtest/ML candle data |
| `strike_forecast_models` | ML model metadata |

---

## 13. Background automation

| Engine | Trigger | UI effect |
|--------|---------|-----------|
| Calendar spread live | ~30s deploy scheduler + tick updates | Auto deploy at IST time; auto exit on stop/target/expiry; WS updates |
| Positions service | WS ticks + 15s refresh | Running PnL updates on Active Positions |
| Strike advisor | Async on demand | Job progress bars |
| Move straddle backtest | Async on POST | Progress → result table |
| Calendar backtest | Async on POST | Progress → equity + trades |

---

## 14. Feature maturity matrix

| Feature | Backtest | Live / Forward | Real orders | History |
|---------|----------|----------------|-------------|---------|
| Calendar Spread | ✅ | ✅ | ✅ (`live_order`) | ✅ |
| Daily Strangle | ✅ | ❌ 501 | ❌ | ❌ empty |
| Strike Advisor | N/A (forecast) | ✅ async | N/A | model metadata |
| Active Positions | — | ✅ broker sync | — | ✅ order history |
| Arbitrage / Spread execution | — | ❌ not in backend | — | — |
| Directional options | — | ❌ not in backend | — | — |
| Market scanner (Top Gainers, Near ATH) | — | ❌ not in backend | — | — |
| Manual order ticket | — | API only | ✅ | — |

---

## 15. Cross-cutting UI rules

- **Timestamps:** API uses UTC ISO (`Z`); Calendar Spread UI displays **IST** for deploy/exit times
- **Money:** USD amounts = **2 decimal places** (premiums, PnL, debit, margin)
- **Quantities:** lots ↔ BTC/ETH conversion (BTC: 1000 lots = 1 BTC; ETH: 100 lots = 1 ETH)
- **Auth:** All routes except `/api/health` require `Authorization: Bearer <token>`
- **Errors:** `{ error, detail, status }` JSON
- **Async jobs:** backtest/forecast return `{ status: "processing" }` immediately; poll REST or wait for WS job update

---

## 16. Suggested UI information architecture

```
App Shell
├── Auth (login/register)
├── Header
│   ├── Nav: Dashboard | Active Positions | Calendar Spread | Daily Strangle | Strike Advisor
│   ├── BTC/ETH spot chips
│   ├── Live connection dot
│   ├── Account selector
│   └── Avatar → Account Settings, Logout
├── Account Settings Modal
│   ├── Profile
│   ├── Trading Accounts (add/delete/select Delta)
│   └── Public IP whitelist card
│
├── Dashboard
│   ├── Balance / PnL summary cards
│   ├── Portfolio chart
│   ├── Open positions snapshot
│   └── Trade history
│
├── Active Positions
│   ├── Open (positions + orders)
│   ├── Past Orders
│   └── Payoff chart modal
│
├── Calendar Spread
│   ├── Backtest (form + results)
│   ├── Live (engine control + multi-set tabs + payoff)
│   └── History (equity + daily grid + run panels)
│
├── Daily Strangle
│   ├── Backtest (form + results)
│   └── Live/History (disabled placeholders)
│
└── Strike Advisor
    ├── Forecast inputs + charts
    ├── Model status + train
    └── Apply to Calendar Spread CTA
```

---

## 17. Gemini Canvas prompt (starter)

> Design a React trading workspace UI for **CryptoBridge** — a Delta Exchange India options automation platform. Backend provides: (1) multi-account auth and wallet balances, (2) a single live WebSocket for prices/positions/strategy state, (3) **Calendar Spread** with backtest + live engine (forward test and real orders), multi-open spread-set tabs, payoff charts, dynamic position sizing, and full history, (4) **Daily Short Strangle** backtest only, (5) **Strike Advisor** ML range forecast with apply-to-calendar flow, (6) unified **Active Positions** across accounts with payoff tooling. Use a clean white header with lime accent, full-width strategy pages, IST time display for options deploy/exit, 2dp USD formatting, and real-time badges. Dashboard aggregates WS snapshot + positions. Account onboarding requires Delta API key + IP whitelist hint.

---

## Related docs

- [FEATURES.md](./FEATURES.md) — complete feature reference (includes planned/legacy areas)
- [architecture.md](./architecture.md) — system diagrams and data flow
- [project-context.md](./project-context.md) — onboarding and conventions

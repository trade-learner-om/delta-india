# CryptoBridge Project Context

## What This Project Is

**CryptoBridge** (folder: `delta`, version `0.1.0`) is a dedicated **Delta Exchange India** trading workspace. It inherits the visual language and UX patterns of **SignalBridge** (a "control room" trading shell) but targets Indian crypto markets via Delta's APIs.

It is **not** a generic Delta SDK — it is a full-stack web app with local auth, Delta account onboarding, watchlist curation, live market pricing, charting, order execution, **Quick Order**, and **Crypto Planner** automation.

**Current maturity:** v0.1 trading workspace — auth, accounts (wallet margin), watchlist, event-driven live prices, tick-size price precision, OHLC charts, risk-based order sizing, copy trading, Quick Order, Crypto Planner, header P/L.

---

## Documentation Map

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Quick start, stack, doc index |
| **[FEATURES.md](./FEATURES.md)** | **Complete feature & API reference (nothing omitted)** |
| [CHANGELOG.md](./CHANGELOG.md) | Chronological functionality changes |
| [DOCUMENTATION-POLICY.md](./DOCUMENTATION-POLICY.md) | **Required doc updates on every feature change** |
| [architecture.md](./architecture.md) | Architecture overview, data flow, diagrams |
| [project-context.md](./project-context.md) | This document — onboarding & conventions |
| [delta-api-capabilities.md](./delta-api-capabilities.md) | Delta Exchange India API reference + coverage matrix |
| [FRONTEND_SMOKE.md](../backend-python/tests/FRONTEND_SMOKE.md) | Manual regression checklist |

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Frontend | React 18, Vite 8, Tailwind CSS 3, PostCSS, `lightweight-charts` |
| Backend (default) | Python 3.9+ FastAPI, Motor, httpx, websockets, **numpy**, **scikit-learn** |
| Backend (legacy) | Java 21 Spring WebFlux in `backend-webflux/` |
| Persistence | MongoDB |
| Security | BCrypt passwords, Bearer session tokens (7-day TTL), AES-GCM for Delta API secrets |
| External | Delta REST (`api.india.delta.exchange/v2`) + India public WS (`public-socket.india.delta.exchange`) |
| Dev orchestration | `scripts/run-backend.sh` / `scripts/run-backend.bat` (`start` \| `stop` \| `restart` \| `status`) |

---

## Repository Layout

```
delta/
├── README.md
├── docs/
│   ├── FEATURES.md              # Complete feature reference
│   ├── CHANGELOG.md
│   ├── DOCUMENTATION-POLICY.md
│   ├── architecture.md
│   ├── delta-api-capabilities.md
│   └── project-context.md
├── scripts/
│   ├── run-backend.sh           # Backend lifecycle (Unix)
│   └── run-backend.bat          # Backend lifecycle (Windows)
├── frontend-react/
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       ├── utils/               # liveMerge, pricePrecision, accountMargin
│       └── components/          # trading, quickorder, planner, charts, ...
├── backend-python/              # Default API (port 8080)
│   └── cryptobridge/
│       ├── routers/
│       ├── services/
│       ├── delta/
│       └── utils/
└── backend-webflux/             # Legacy reference implementation
```

---

## Product Features (Implemented)

See [FEATURES.md](./FEATURES.md) for exhaustive detail. Summary:

| Area | Highlights |
|------|------------|
| Auth | Register/login, 7-day sessions |
| Accounts | Delta onboarding, wallet margin/balance, master + planner risk, public IP whitelist hint |
| Watchlist | BTC/ETH/SOL defaults, purge invalid symbols, tick-based `price_digits` |
| Live data | Delta public WS → backend relay → `/ws/live` |
| Trading | MT5 layout, chart, SL/LIMIT/MARKET, copy trade, risk preview, candle detector |
| Quick Order | Candle entry/SL, $10 / 1% max risk cap, history + sync |
| Planner | Pivot strategy, trap, targets, 3R breakeven, 8R default exit |
| Positions | Open orders + cancel |
| Precision | All prices from Delta `tick_size` (BTC/ETH: 2dp, SOL: 3dp, auto for new symbols) |

**Frontend pages:**

| `currentPage` | UI |
|---------------|-----|
| `trading` | Watchlist + chart + order ticket |
| `quick-order` | Quick order form + history |
| `planner` | Watchlist + plan list + create/stop |
| `positions` | Orders table |

---

## API Surface (summary)

Full reference: [FEATURES.md §12](./FEATURES.md#12-rest-api-reference).

**REST groups:** auth, accounts, watchlist, instruments, chart, orders, risk-preview, planner, quick-orders, dashboard/health.

**WebSocket:** `/ws/live` — `snapshot`, `price`, `planner`, `quick_order`.

---

## MongoDB Collections

| Collection | Purpose |
|------------|---------|
| `app_users` | Local users + session tokens |
| `delta_accounts` | Delta API credentials + risk fields |
| `watchlist_items` | Per-user symbols + `priceDigits` / `tickSize` |
| `planner_sessions` | Planner state machine + activities |
| `quick_orders` | Quick order history + P/L sync |
| `retryable_orders` | Trade retryable order tracking + stop-out retry |

Schemas: [FEATURES.md §14](./FEATURES.md#14-data-model-mongodb).

---

## Configuration

| Variable | Default | Used by |
|----------|---------|---------|
| `MONGODB_URI` | `mongodb://localhost:27017/cryptobridge` | Backend |
| `PORT` | `8080` | Backend |
| `DELTA_API_BASE_URL` | `https://api.india.delta.exchange` | Delta REST |
| `DELTA_PUBLIC_WS_URL` | `wss://public-socket.india.delta.exchange` | Market WS |
| `CRYPTOBRIDGE_CRYPTO_SECRET` | `cryptobridge-dev-secret` | API secret encryption |
| `VITE_API_BASE` | `https://crypto.api.signalbridge.in/api` | Frontend REST |
| `VITE_WS_BASE` | `https://crypto.api.signalbridge.in` | Frontend WS |
| `LOG_TO_FILE` | `true` | Rotating file log (default; no stdout) |
| `LOG_DIR` | `{repo_root}/logs` | Local log folder (gitignored) |
| `LOG_FILE` | `cryptobridge.log` | Main backend log filename |
| `LOG_MAX_BYTES` | `10485760` | Rotate at 10 MB |
| `LOG_BACKUP_COUNT` | `5` | Rotated backups kept |
| `LOG_LEVEL` | `INFO` | Root log level |
| `LOG_FORMAT` | `text` | `text` or `json` |

**Delta signed REST:** HMAC timestamps must be within 5 seconds of Delta server time. Keep the host clock NTP-synced (on Windows EC2: Windows Time service / `w32tm /query /status`). The backend also retries once on `expired_signature` and learns a clock offset from error responses.

---

## How to Run

```sh
cd delta
./scripts/run-backend.sh start    # backend
cd frontend-react && npm run dev    # frontend (separate terminal)
./scripts/run-backend.sh status
./scripts/run-backend.sh stop
```

Windows backend: `scripts\run-backend.bat start`

Backend logs go to `logs/cryptobridge.log` by default (rotating, gitignored). Tail in Git Bash: `tail -f logs/cryptobridge.log`. Set `LOG_TO_FILE=false` in `backend-python/.env` for console-only output.

**Tests:** `cd backend-python && pytest`  
**Manual:** [FRONTEND_SMOKE.md](../backend-python/tests/FRONTEND_SMOKE.md)

---

## Key Patterns and Conventions

1. **Python backend** — `scripts/run-backend.sh` or `scripts/run-backend.bat`; Java is legacy reference
2. **Session tokens in MongoDB** — UUID bearer, 7-day expiry (not JWT)
3. **Delta onboarding** — signed `GET /v2/profile` before storing keys
4. **Secrets encrypted** — AES-GCM; keys masked in API responses
5. **One Delta public WS** — shared across all users' watchlist symbols
6. **Event-driven prices** — no frontend polling for watchlist
7. **Risk-based sizing** — server computes quantity; client `size` ignored
8. **Tick-size precision** — `price_digits` from product `tick_size`, not live price decimals
9. **Wallet margin** — USD/USDT/INR preference + `net_equity` fallback
10. **Doc policy** — any feature change updates [FEATURES.md](./FEATURES.md) + [CHANGELOG.md](./CHANGELOG.md)

---

## Domain Terminology

| Term | Meaning |
|------|---------|
| CryptoBridge | This app |
| SignalBridge | Reference UI product |
| Delta Exchange India | Target exchange (India REST + WS endpoints) |
| Workspace | `INDIAN_CRYPTO` (only active market) |
| Selected account | Active Delta account; required for watchlist |
| Snapshot | Full state on `/ws/live` connect or `GET /dashboard` |
| Quick Order | One-shot candle-based order with per-order risk |
| Planner | Automated pivot / structure-break strategy |
| `price_digits` | Decimal places from Delta `tick_size` |
| `available_margin` | Wallet balance available for trading (USD row or net equity) |

---

## What's Not Built Yet

See [delta-api-capabilities.md](./delta-api-capabilities.md). Highlights:

- Private Delta WebSocket (orders, fills, margins push)
- Full positions UI (beyond open orders table)
- Order book, trade tape, live candlestick WS
- Production deployment (Docker, CI/CD)
- Broad HTTP/integration test coverage

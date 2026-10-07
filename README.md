# CryptoBridge

CryptoBridge is a **Delta Exchange India** trading workspace: local auth, multi-account onboarding, live watchlist, charting, order execution, Quick Order, and Crypto Planner automation.

**Version:** 0.1.0

## Quick start

**Prerequisites:** Node.js + npm, Python 3.9+, MongoDB.

**Backend** (creates venv on first `start`):

```sh
# macOS / Linux
./scripts/run-backend.sh start
./scripts/run-backend.sh status
./scripts/run-backend.sh stop
./scripts/run-backend.sh restart
```

```bat
REM Windows
scripts\run-backend.bat start
scripts\run-backend.bat status
scripts\run-backend.bat stop
scripts\run-backend.bat restart
```

**Frontend** (separate terminal):

```sh
cd frontend-react
npm install
npm run dev
```

| Service | URL |
|---------|-----|
| Frontend | https://crypto.signalbridge.in (or `http://localhost:5173` locally) |
| Backend API | https://crypto.api.signalbridge.in/api |
| Backend health | https://crypto.api.signalbridge.in/api/health |
| WebSocket | wss://crypto.api.signalbridge.in/ws/live |
| MongoDB | mongodb://localhost:27017/cryptobridge |

On Windows, `run-backend.bat start` opens the server in a new Command Prompt window. First run installs Python dependencies automatically.

### API endpoints

Production backend: **https://crypto.api.signalbridge.in**

Frontend defaults to this API via `frontend-react/.env`. For local backend development, create `frontend-react/.env.local`:

```env
VITE_API_BASE=http://localhost:8080/api
VITE_WS_BASE=http://localhost:8080
```

### Public / LAN access (local backend)

Backend listens on **all interfaces** (`0.0.0.0`). Frontend dev server also binds to `0.0.0.0` (port **5173**).

1. Start backend: `scripts\run-backend.bat start` (prints LAN URL)
2. Start frontend: `cd frontend-react && npm run dev`
3. Open `http://<your-public-or-lan-ip>:5173` in a browser

The UI automatically uses the same hostname for API/WebSocket calls (port **8080**). Override with `VITE_API_BASE` / `VITE_API_PORT` if needed.

**Firewall:** allow inbound TCP **8080** (API/WS) and **5173** (frontend).

**Delta API keys:** whitelist this server's **outbound** public IP (see Manage Account in the app).

Tests: `cd backend-python && pytest`

## Product surface (summary)

| Area | Capabilities |
|------|----------------|
| **Auth** | Register, login, session tokens |
| **Accounts** | Add/delete Delta accounts, select active, wallet margin/balance, per-account risk, **public IP for Delta whitelist** |
| **Trading** | Watchlist, live prices, OHLC chart, SL/LIMIT/MARKET orders, copy trade (2 accounts), risk preview |
| **Quick Order** | Candle-based entry/SL, per-order risk, **$10 / 1% max risk cap**, history + P/L |
| **Planner** | Pivot strategy on 1m, trap mode, targets, breakeven at 3R, stop with optional close |
| **Positions** | Open orders table, cancel pending |

## Documentation

| Document | Description |
|----------|-------------|
| **[FEATURES.md](./docs/FEATURES.md)** | **Complete feature & API reference** (start here) |
| [CHANGELOG.md](./docs/CHANGELOG.md) | What changed and when |
| [DOCUMENTATION-POLICY.md](./docs/DOCUMENTATION-POLICY.md) | Rules for keeping docs updated |
| [architecture.md](./docs/architecture.md) | System design and data flows |
| [project-context.md](./docs/project-context.md) | Onboarding, config, conventions |
| [delta-api-capabilities.md](./docs/delta-api-capabilities.md) | Delta API catalog vs app coverage |
| [FRONTEND_SMOKE.md](./backend-python/tests/FRONTEND_SMOKE.md) | Manual regression checklist |

## Stack

- **Frontend:** React 18, Vite, Tailwind, lightweight-charts
- **Backend:** Python FastAPI, Motor (MongoDB), httpx, websockets
- **Exchange:** Delta Exchange India REST + public WebSocket (backend only)

Legacy **Java WebFlux** backend remains in `backend-webflux/` for reference only.

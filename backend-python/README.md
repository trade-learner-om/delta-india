# CryptoBridge Python Backend

FastAPI service for Delta Exchange India integration.

**Full API & feature reference:** [../docs/FEATURES.md](../docs/FEATURES.md)

## Run

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python3 -m cryptobridge.server
# Dev with reload: UVICORN_RELOAD=true python3 -m cryptobridge.server
```

From repo root:

- **Backend:** `./scripts/run-backend.sh {start|stop|restart|status}` (Windows: `scripts\run-backend.bat`)

## Environment

| Variable | Default |
|----------|---------|
| `MONGODB_URI` | `mongodb://localhost:27017/cryptobridge` |
| `PUBLIC_API_BASE_URL` | `https://crypto.api.signalbridge.in` |
| `CORS_ALLOWED_ORIGINS` | `https://crypto.signalbridge.in,http://localhost:5173,...` |
| `DELTA_API_BASE_URL` | `https://api.india.delta.exchange` |
| `DELTA_PUBLIC_WS_URL` | `wss://public-socket.india.delta.exchange` |
| `CRYPTOBRIDGE_CRYPTO_SECRET` | `cryptobridge-dev-secret` |

Copy [`.env.example`](.env.example) to `.env` for local overrides.

## Package layout

```
cryptobridge/
├── main.py           # App lifespan, CORS, router wiring
├── config.py
├── routers/          # auth, accounts, orders, positions, meta, live
├── services/         # auth, accounts, orders, positions, snapshot
├── delta/            # REST client + public/private WebSocket
└── utils/            # risk_sizing, risk_limits, positions_helpers, crypto, signing
```

## Tests

```sh
pytest
```

Manual frontend checklist: [tests/FRONTEND_SMOKE.md](tests/FRONTEND_SMOKE.md)

## Documentation

When changing behavior, update [../docs/FEATURES.md](../docs/FEATURES.md) and [../docs/CHANGELOG.md](../docs/CHANGELOG.md) per [../docs/DOCUMENTATION-POLICY.md](../docs/DOCUMENTATION-POLICY.md).

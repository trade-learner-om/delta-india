# SuperTrend Perp (ST Perp)

**Product:** BTC / ETH perpetual futures  
**UI route:** `st-perp` nav (**ST Perp**)  
**Timeframe:** 90m IST-aligned bars (15m aggregate) + 1m intrabar  
**Code:** `services/st_perp_engine.py`, `services/st_perp_service.py`, `services/st_perp_backtest_service.py`

---

## Entry (tap → confirm)

**Arm on 90m ST flip.** Use **prior closed 90m bar** SuperTrend line for tap test (no lookahead).

| Armed ST | 1m wick tap | 1m close confirm | Side | Initial SL |
|----------|-------------|------------------|------|------------|
| **Green** | `low <= ST` | `close > ST` | **LONG** | Confirm candle **low** (min **$1** below entry) |
| **Red** | `high >= ST` | `close < ST` | **SHORT** | Confirm candle **high** (min **$1** above entry) |

**Sizing:** `floor(maxRisk / (|entry − SL| × contract_value))` whole contracts. **Skip** the entry when that formula yields &lt; 1 contract (one lot would risk more than `maxRisk` — e.g. $10 max risk with a $3,000-wide ETH stop would lose ~$30 at SL).

**SuperTrend defaults:** period **8**, multiplier **3.0** on 90m bars (configurable in backtest and live settings).

---

## Exits (configurable)

| Leg | Default | Trigger |
|-----|---------|---------|
| **TP1** | 30% at **3R** | Price reaches `target3r × R` |
| **TP2** | 30% at **10R** | Price reaches `target10r × R` |
| **Runner** | remainder | Opposite 90m ST flip — fill at **stop or better**, not raw 90m close (toggle **exitOnStFlip**) |

Stop loss: initial bracket on entry candle H/L (min `minSlDistanceUsd` from entry, default **$1**).

---

## API

| Method | Path |
|--------|------|
| GET | `/api/st-perp/meta` |
| POST | `/api/st-perp/start` | `{ symbol, maxRiskAmount, minSlDistanceUsd?, stPeriod?, stMultiplier?, partial3rPct?, partial10rPct?, target3r?, target10r?, exitOnStFlip? }` |
| POST | `/api/st-perp/stop` |
| GET | `/api/st-perp/live` |
| GET | `/api/st-perp/history` |
| POST | `/api/st-perp/backtest` | async job |

**WebSocket:** `type: st_perp_session` — `setups[]`, `active[]`, `backtestJob`.

---

## MongoDB

| Collection | Purpose |
|------------|---------|
| `st_perp_setups` | Scanner config (risk, ST period/multiplier, exit plan) |
| `st_perp_trades` | Open/closed perp positions |

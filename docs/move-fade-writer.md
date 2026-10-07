# Move Fade Writer

Delta-only options strategy: fade sharp BTC moves from the **6:30 PM IST** anchor by writing OTM options after an hourly confirmation.

## Rules (modeled in backtest)

| Rule | Value |
|------|--------|
| Anchor | BTC price at **6:30 PM IST** each day |
| Up trigger | Configurable % up from anchor (e.g. 4.5%) → sell **OTM CALL** |
| Down trigger | Configurable % down from anchor (e.g. 6%) → sell **OTM PUT** |
| Entry timing | On first threshold touch, **lock in**, then sell at the **next Delta hourly close** (candles end on **:30** UTC) |
| Live default strike | **OTM 5** (backtest sweeps ITM10…ATM…OTM10) |
| Expiry | Nearest Delta BTC expiry after entry; if entry is **after 9:00 AM IST**, use **next day's** expiry |
| Stop loss | Exit when premium rises to **130%** of entry (30% loss on premium) |
| Take profit | Exit at **80% premium decay** (premium = 20% of entry) |
| Re-entry | After SL, re-place the same contract **once**; stop after second SL |
| Settlement | Unclosed legs settle at expiry intrinsic value |

## Backtest (phase 1)

**Page:** `MoveFadeWriterPage` (nav **Move Fade**).

### Move Study tab

- Histogram-style table of max up/down % from the daily anchor.
- Hit rates for separate up/down thresholds.
- Count of first-touch triggers (CALL vs PUT) and entries after 9 AM IST.

**API:** `POST /api/move-fade/move-study`

```json
{
  "startDate": "2025-01-01",
  "endDate": "2025-03-01",
  "upMovePct": 4.5,
  "downMovePct": 6.0
}
```

### Strike Ladder tab

For each triggered day, simulates writing every offset **ITM10 … ITM1, ATM, OTM1 … OTM10** using Delta **historical option candles** (`/v2/history/candles` per contract). Aggregates win rate, avg/total PnL, SL/TP/expiry rates, and re-entry count per offset. **OTM5** row highlighted as the live default.

**API:** `POST /api/move-fade/backtest`

```json
{
  "startDate": "2025-01-01",
  "endDate": "2025-03-01",
  "upMovePct": 4.5,
  "downMovePct": 6.0,
  "quantity": 1,
  "contractValue": 0.001,
  "optionResolution": "5m"
}
```

## Implementation

| Piece | Path |
|-------|------|
| Pure engine | `backend-python/cryptobridge/utils/move_fade_backtest.py` |
| Service | `backend-python/cryptobridge/services/move_fade_service.py` |
| Router | `backend-python/cryptobridge/routers/move_fade.py` |
| Frontend | `frontend-react/src/components/movefade/MoveFadeWriterPage.jsx` |
| Tests | `backend-python/tests/test_move_fade_backtest.py` |

## Live automation (future)

Not implemented in phase 1. Will reuse the same rules with Delta REST/WS for order placement on a connected Delta account.

## Data limits

- Backtest depth depends on how far Delta serves **expired option** candle history.
- Days or offsets without option candles are skipped and reported in coverage stats (`tradesSkipped`, `skippedDaysNoExpiry`).
- Max backtest span: **120 days** per request.

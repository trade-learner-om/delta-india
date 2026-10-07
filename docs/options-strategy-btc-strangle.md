# BTC Options Short Strangle

Automated Delta Exchange India 0DTE short strangle strategy. **Underlying is configurable** (BTC default; ETH and other assets with today's option chain supported).

## Parameters (defaults)

| Parameter | Default |
|-----------|---------|
| Underlying | BTC (configurable — ETH, SOL, etc. when listed by `GET /api/options/underlyings`) |
| Entry time | 13:30 IST |
| Exit time | 17:00 IST |
| Lots per leg | 200 |
| Premium threshold | > 62 |
| Entry stop | `ceil(selected_premium - 2)` |
| Stop loss | `ceil(fill_price * 1.60)` |

## Flow

1. Wait until entry time (or run immediately if started after entry time).
2. Select call and put with premium >= threshold, choosing the strike whose premium is closest to the threshold.
3. Place stop-sell entry orders for both legs.
4. On fill, place stop-loss buy orders at premium + 60%.
5. Monitor running/booked PnL and live CE/PE premiums.
6. At 5:00 PM IST, market-close surviving legs.

## Live prices

- **Backend:** On strike selection and session restore (including after backend restart), the runner subscribes Delta market WS to each leg instrument plus `{underlying}USD` spot (e.g. `BTCUSD`, `ETHUSD`).
- **WebSocket `options_strategy`:** Primary source for leg `live_premium`, session `spot`, and running PnL on the Options page.
- **WebSocket `price`:** Global tick feed (`livePrices` in the app). The leg table and PnL panel use it as a fallback when leg premiums in `options_strategy` are stale; the PnL panel shows live spot between Entry/Mark Premium cards; the header shows `BTC {price}` from `BTCUSD`.
- **Pre-fill PnL:** For legs in `selected` or `entry_placed`, Running PnL uses theoretical short PnL: `(picked_premium − live_premium) × qty × contract_value`.

## API

- `GET /api/options/underlyings`
- `GET /api/options/chain`
- `POST /api/options/strike-preview`
- `POST /api/options/strategies/start`
- `POST /api/options/strategies/stop`
- `GET /api/options/strategies`
- `GET /api/options/strategies/active`

## UI

Navigate to **Options** in the header to start and monitor sessions.

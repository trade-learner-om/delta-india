# 1H SuperTrend Options Sell (ST Options)

**Product:** Short-vol options on BTC / ETH  
**UI route:** `st-options` nav (**ST Options**)  
**Timeframe:** Closed **1H** bars (Delta `1h`)  
**Code:** `utils/st_options_indicators.py`, `utils/st_options_resolver.py`, `utils/st_options_strategy.py`, `utils/st_options_backtest.py`, `services/st_options_service.py`, `routers/st_options.py`

---

## Indicators (TradingView parity)

| Indicator | Default | Base |
|-----------|---------|------|
| EMA | 10 | Close — SMA seed over first `length` bars (`ta.ema`) |
| SuperTrend | 10, 3 | **HL2** — RMA ATR (`ta.atr`), Pine `ta.supertrend` band pinning + direction state machine |

Indicators use **120 days** of 1H history before the visible window (live + backtest) so values match TradingView.

**SuperTrend algorithm:**
- Source: `hl2 = (high + low) / 2`
- Pinning vs **prior** final upper/lower bands
- Direction: Pine state machine on close vs current pinned bands
- Line: lower when green, upper when red
- First ATR bar initializes **red on upper band**

---

## Strategy

### Long (sell PUT)

1. Price closes **above** ST → long sentiment  
2. Price closes **below EMA** but still **above ST** → entry  
3. **Live + backtest:** `|close − ST line| / close × 100` must be **&lt; `maxStDistancePct`** (default **0.3**; **0** = off)  
4. Sell PUT via OTM-first waterfall across eligible expiries (min premium % of perp). **Live** uses **ATM±1** and requires ticker volume &gt; the band average; **backtest `min_pct`** still uses OTM3→ITM3.

### Short (sell CALL)

Mirror of Long.

### Exits

| Exit | Rule |
|------|------|
| ST flip | Perp 1H close on opposite side of ST |
| Stop loss | Option premium ≥ entry + **Stop loss %** (default 105% → **2.05×** premium received) |
| Take profit | Option premium melts by **Take profit %** (default 95% → **5%** remaining) |
| Expiry close | Same-day contract: market square-off at **17:15 IST** (`expiry_close`); re-entry allowed if criteria still hold |
| Settled | Past **17:30 IST** settlement: mark closed at intrinsic (`expired`) — no broker reduce |
| Force closed | Operator **Force close** when broker close fails (contract missing) — DB only |

Backtest evaluates SL/TP on option candle **high/low** (SL before TP if both touch). Backtest also force-closes on the last 1H bar closing at/before 17:15 IST on the expiry day.

Live and backtest accept **Stop loss (% premium rise)** (`stopLossPct`, default 105 → 2.05×) and **Take profit (% premium melt)** (`takeProfitPct`, default 95 → 5% remaining). Values apply to new entries; changing settings does not amend an already-open trade.

After a live **limit-sell** fill (limit at live mark/last − $1; lots sized from that limit and configured `stopLossPct` **widened 40% for stop-market slippage**; skipped when one lot would exceed `maxRisk`), the engine attaches a Delta position bracket with **stop-market** SL and TP (trigger only, never a limit cap) and stores both leg IDs. Fill confirmation polls the order, **retries cancel** (order id + cancel-all for that product) until cancelled/filled/gone, re-fetches, checks recent **sell fills**, and multi-tries margined positions before giving up. A leftover working limit is **cancelled on reconcile** — 404 is not treated as “keep watching.” Unfilled pending rows clear after ~3 empty confirms without waiting the old 150s min-age while the order was still open. Unhedged live PnL ≤ **−maxRisk** flattens immediately (`max_loss`) even if broker SL is attached. While the engine is on, each tick also **adopts unprotected short options** on the configured underlying that are not already tracked and attaches SL/TP; open trades missing brackets get a retry. Broker fills (`CLOSED` / `FILLED`) are reconciled into trade history without sending a second reduce order. If bracket attachment or leg discovery fails, the engine falls back to mark/last monitoring and a market reduce. On ST flip, manual stop, expiry close, settlement, or force close, pending bracket legs are cancelled before the strategy exit proceeds; cancel failures keep the broker IDs and block the market reduce so a live stop/target cannot be orphaned against a second reduce.

### Backtest data / diagnostics

- Prefetch option 1H candles for strikes spanning **min→max** window perp close ± 3 steps (OTM/ITM band).
- Missing waterfall symbols are **lazy-fetched** when a signal resolves.
- Result includes `diagnostics`: `barsInWindow`, `entrySignals`, `opened`, `skippedNoContract`, `skippedNoPremium`, `skippedFormation`, `skippedAfterTarget`. UI shows a one-line note when opened = 0.

### Re-entry

After **take profit** or **expiry close**: if entry criteria still hold, enter again with the same rules (post-17:15 entries use T1 only).

**Backtest only — `oneTradePerFormation`:** when on (default off), after **any** close on a side, that side will not re-enter until `st_colour` changes. Long and Short are independent. Disables same-colour TP re-entry.

**Backtest only — `skipSetupsAfterTarget`:** after a **take_profit** exit on a side, skip the next N entry signals on that side (default **1**, `0` = off). Other exit reasons do not arm this skip. Independent of `oneTradePerFormation` (both can apply).

**Pair hedge:**
- **Live (`pairHedgeDecayPct`):** default **0** = off. When &gt; 0, after the main short melts that %, limit-sell the same-strike opposite option (same lots/expiry). Editable while the engine is running; if decay is already met when armed, hedge opens on the next manage tick. Setting to 0 leaves an open hedge as-is (no new hedges). Main TP/SL/ST-flip/expiry/manual/force close exits both. Combined unrealized PnL of main + hedge ≤ **−maxRisk** flattens both (`max_loss`). At hedge fill, freeze **`hedgeStopPremium = hedgeEntry + (mainProfit$ + maxRisk) / (cv × lots)`** (not amended later); attach broker SL-only on the hedge as a safety net if main TP fails to square both.
- **Backtest (`pairHedgeEnabled`):** when on, each main short also shorts the same-strike opposite option. Modes: **`immediate`** (open both; exit on PE≈CE parity or main SL; no solo TP) or **`on_decay`** (open opposite after main melts `pairHedgeDecayPct`, then both exit on main target/SL). Off → single-leg as today.

### Concurrency

One open **Long** and one open **Short** may coexist (not two Longs).

---

## Strike / expiry waterfall

### Live and backtest `min_pct` (default)

1. Eligible expiries: **T1** always; **T0** only when the signal bar’s close IST time is **≤ 10:30**  
2. Ladder per expiry: **Live — OTM1 → ATM → ITM1.** **Backtest `min_pct` — OTM3 → … → ATM → … → ITM3**  
3. Collect every strike with premium ≥ `minPremiumPct` of perp. **Live:** load Delta ticker `volume` for that ATM±1 band (same side, T0/T1); keep only **volume &gt; average** (missing/zero included). If none (or all zero), skip: “Setup skipped — no liquid strike (ATM±1).” Among remaining, pick **furthest OTM**, ties → **later expiry (T1)**. **Backtest:** no volume gate; furthest OTM, ties → T1.  
4. Strike steps: BTC **200**, ETH **20**  
5. Product fetch uses Delta `/v2/products?expiry=YYYY-MM-DD`; symbols that do not match that day are ignored. Live orders only place `resolved.symbol` when its day is eligible.

### Backtest-only strike modes (`strikeSelectMode`)

Mutually exclusive; live engine always uses the % waterfall.

| Mode | Value | Behavior |
|------|--------|----------|
| Strike type | `fixed` | Exact moneyness `OTM10`…`ATM`…`ITM10`. Expiry automatic: bar-close IST **&lt; 05:30 → T0**, else **T+1**. No T+2; no fallback if that day’s premium is missing. |
| Min % of underlying | `min_pct` | Same waterfall as live (above). |
| SuperTrend line | `supertrend` | ATM snapped to ST line; existing T0/T1 eligibility. |
| Minimum premium | `min_abs` | Waterfall with absolute floor `minPremiumAbs` (depth 10). |

### Live Start / Stop / Force close

- **Turn on (`POST /api/st-options/start`):** Accepts optional settings body and enables the engine in one write. Arms the strategy only — open position cards appear after a closed **1H** bar meets entry rules and the waterfall finds a contract.
- **Live hedge hot-toggle:** Changing `pairHedgeDecayPct` via PATCH while enabled applies on the next manage pass immediately (and each engine tick re-reads Mongo). Strategy settings UI keeps the field editable while on and does not clobber in-progress edits with WS snapshots.
- **Turn off (`POST /api/st-options/stop`):** Closes every open ST Options trade (market buy-to-cover, `exitReason: manual_stop`) **only when the reduce order succeeds**, then sets `enabled: false`. Failed closes stay `open` and are retried once; response may include `closeFailures[]` (`product_missing` / `close_failed`). Leftover panel offers **Close positions** and, after a no-contract failure, **Force close**.
- **Force close (`POST /api/st-options/trades/{id}/force-close`):** Marks an open trade closed in Mongo (`exitReason: force_closed`) without a broker order — use when the contract no longer exists.
- Engine auto square-off at **17:15 IST** for same-day expiries; auto-settle after **17:30 IST**.
- Deploy alone does **not** retroactively close prior opens — press Turn off, Close positions, or Force close after deploy.
- WS `st_options_session` merges ignore unstamped/older snapshots so `active` cannot resurrect after Stop.

---

## User-facing glossary (Live UI)

End users see calm desk language. Mechanics stay in this doc, **Advanced** settings, and server logs.

| User sees | Means (operators) |
|-----------|-------------------|
| Strategy on / off · Turn on / Turn off | Engine `enabled` start/stop |
| Market watch | Engine status panel (phase, readiness, countdown, updates) |
| Looking for a setup | Phase `watching` |
| Setup ready — waiting for the next hour | Phase `entry_ready` |
| Managing open positions | Phase `managing_opens` |
| Bias: Up / Down | SuperTrend green / red |
| Long-side / Short-side trade | Sell PUT / sell CALL |
| Max risk ($) | `maxRisk` — live + backtest; live lots from limit (mark−1) × stopLossPct **× 1.4 slippage buffer**; skip if 1 lot > maxRisk; unhedged live PnL ≤ −maxRisk flattens |
| Minimum option price (%) | Min premium % of perp |
| Protect at / Target | Stop premium (2.05×) / take-profit (0.05×) |
| Market flipped / Stop / Target / Closed manually / Max loss / Pair exit | `st_flip` / `stop_loss` / `take_profit` / `manual_stop` / `max_loss` / `pair_stop` |
| Closed before expiry / Settled at expiry / Force closed | `expiry_close` / `expired` / `force_closed` |
| Updates feed | Activity `userMessage` only (technical `message` kept for support) |
| Not active while bias is down / up | Opposite side sits out (bias already set the other way) |

**Live settings:** Gear opens **Strategy settings** modal (Underlying / Max risk $ / Minimum option price % / Stop loss % / Take profit % / Hedge after decay %). While the strategy is on, only **Hedge after decay %** remains editable. **Advanced** (Live modal + Backtest) requires a confirm warning — changing ST/EMA is not recommended — before ST period/mult and EMA fields appear.

---

## Troubleshooting logs

Live UI is plain by design. For forensics, grep server logs for the prefix **`ST Options:`**.

Typical lines include:

- start / stop (userId, underlying, qty, minPremiumPct, leftovers)
- each newly processed 1H bar (barTime IST, close, ema, stLine, stColour, longReady, shortReady)
- entry signal, open fill (symbol, strike, expiry, premiums, orderId)
- skip reasons: `no_premium_or_contract`, `not_t0_t1`, `product_missing`, `order_failed`
- close success/fail (reason, exit premium, pnl, orderId)

Activity buffer stores dual fields: technical `message` + plain `userMessage`. Live renders **`userMessage`** only.

---

## Settings (live + backtest)

| Setting (UI) | Internal / default |
|--------------|-------------------|
| Underlying | BTC / ETH |
| Max risk ($) | `maxRisk` · 100 — live + backtest; live sizes from limit (mark−1); backtest from resolved premium |
| Minimum option price (%) | `minPremiumPct` · 5 (live always; backtest when mode = `min_pct`) |
| Strike selection (backtest) | `strikeSelectMode` · `min_pct` — also `fixed` / `supertrend` / `min_abs` |
| Strike type (backtest `fixed`) | `strikeType` · `ATM` (OTM10…ITM10); expiry auto via 05:30 IST |
| Minimum premium abs (backtest `min_abs`) | `minPremiumAbs` · 50 |
| One trade per ST formation (backtest) | `oneTradePerFormation` · off |
| Skip next setup after Target (backtest) | `skipSetupsAfterTarget` · 1 (0 = off); arms only on take_profit |
| Max close→ST distance % (live + backtest) | `maxStDistancePct` · 0.3 (0 = off); `|close−ST|/close×100` must be &lt; threshold |
| Pair hedge (live) | `pairHedgeDecayPct` · 0 (0 = off; editable while running); frozen `hedgeStopPremium` at open |
| Pair hedge (backtest) | `pairHedgeEnabled` · off; `pairHedgeMode` immediate \| on_decay; `pairHedgeDecayPct` · 40 |
| Stop loss (% premium rise) | `stopLossPct` · 105 (also drives backtest lot sizing) |
| Take profit (% premium melt) | `takeProfitPct` · 95 (must be below 100 for live broker target) |
| Move SL to BE after decay % | `breakevenDecayPct` · 40 (0 = off) |
| Trend length / sensitivity / pullback filter (Advanced) | ST period/mult · EMA length · 10 / 3 / 10 |
| Backtest from / to | default **today−7 IST → today IST**; outside gear |
| Dynamic position sizing (backtest only) | Off by default; after N losses +% of base `maxRisk` (cap maxRisk%); after M profits −% (floor = base) |

Live settings live in `st_options_config`. Backtest settings live in `st_options_backtest_config` (separate).

Fixed (not settings) for live: ATM±1 + volume &gt; band average, T0/T1 expiry search. Backtest `min_pct` still uses ITM/OTM depth 3. `fixed` mode uses its own 05:30 expiry rule.

Lots are derived from max risk (not a fixed coin quantity). **Live:** sell limit at live mark/last − $1; size from that limit and configured `stopLossPct` **widened 40%**; skip when one lot’s buffered SL risk would exceed `maxRisk`; **cancel leftover limits quickly** (retry until gone — do not leave a working limit for a late fill). Broker SL is stop-market. **Backtest:** still sizes from resolved premium (simulated, no buffer). Contract value: BTC 0.001 / ETH 0.01 per lot.

---

## UI

- **Live → Running:** Compact Strategy on/off + **Total PnL** + gear (**Strategy settings** modal) + Turn on/off; header As of / Bias arrow / Market; compact live summary KPIs; **Market watch** (phase, long/short readiness, next-decision countdown, Updates in IST); open position cards when filled — Bias from trade/live ST, plus Open (est.) / Est. loss (stop) / Est. profit (target)  
- **Settings (live):** Stop loss %, Take profit %, **Move SL to BE after decay %**, **Max close→ST distance %**  
- **Live → History:** closed live trades with plain exit reasons  
- **Backtest:** From / To + Run outside; gear modal for **Max risk $** + strike modes + formation toggle + skip-after-Target + max close→ST distance % + dyn % sizing; saved runs picker; **Compare**; progress via WS; richer summary KPIs; trade table with **Quantity** (lots)  
- **Quantity:** Running cards, History/Backtest table, and Dashboard Recent Trades show lot count  

Live Running uses a soft page-wide green/red bias wash (`st-options-page--*`). No orphan empty card while on and flat — Market watch phase covers that. Poll / last-processed-bar / EMA–ST line numbers are **not** shown on the default Running view.

Opposite-side Market watch copy: **Not active while bias is down/up** (instead of “waiting for” the opposite bias).

**Backtest summary:** total trades / PnL, wins / losses, max winning/losing streak as `len(count)` (e.g. `4(2)`), avg profit / avg loss, long/short counts + PnL, max profit/loss (+date), max drawdown, max DD duration.

**Row columns:** Date | Side | Lots | Bias | Bias changed | Strike | Expiry | Received | Exit | Reason | Result

---

## API

| Method | Path |
|--------|------|
| GET | `/api/st-options/meta` |
| GET/PATCH | `/api/st-options/config` |
| POST | `/api/st-options/start` \| `/stop` |
| GET | `/api/st-options/live` |
| GET | `/api/st-options/history` |
| GET/PATCH | `/api/st-options/backtest/config` |
| GET | `/api/st-options/backtest/runs` |
| GET/DELETE | `/api/st-options/backtest/runs/{id}` |
| POST | `/api/st-options/backtest` |
| GET | `/api/st-options/backtest/job` |

**WebSocket:** `type: st_options_session` (`topic: st_options`) — `config`, `active[]`, `indicator`, `status` (phase / readiness / dual activity), `backtestJob` (may include `runId`).

---

## MongoDB

| Collection | Purpose |
|------------|---------|
| `st_options_config` | Per-user live settings + `enabled` |
| `st_options_trades` | Open + closed live trades |
| `st_options_backtest_config` | Per-user backtest settings (incl. maxRisk, dyn % sizing, strike modes, formation gate) |
| `st_options_backtest_runs` | Saved backtest results (keep last ~50 / user) |

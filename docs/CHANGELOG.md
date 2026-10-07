# Changelog

All notable functionality changes to CryptoBridge.  
Format follows [DOCUMENTATION-POLICY.md](./DOCUMENTATION-POLICY.md). Newest first.

---

## 2026-08-17 — Cap live max loss and cancel leftover entry limits

### Changed
- **Live lot sizing:** Size as if stop-loss % were **40% wider** so stop-market slippage stays near `maxRisk` (backtest buffer stays 0). Broker SL/TP remain **stop-market** (trigger only — never stop-limit).
- **Unhedged max-loss flatten:** When live short PnL ≤ **−maxRisk**, flatten the main even if broker brackets are attached (same `max_loss` path as hedged pairs), before waiting on the broker SL fill.
- **Live strikes:** ATM±1 only (OTM1 / ATM / ITM1). Keep only strikes whose ticker **volume &gt; average of that band** (missing/zero included). Skip with “no liquid strike (ATM±1)” if none pass. Backtest `min_pct` waterfall stays OTM3.
- **Unfilled entry limits:** After the short wait, retry cancel (order id + cancel-all) until gone or filled. Reconcile **cancels** still-open pending limits instead of leaving them on the book. 404 is not “keep watching.” Updates copy is “Limit cancelled — setup skipped.”

---

## 2026-08-14 — Dashboard equity wave + active desks empty

### Fixed
- **Equity Performance Wave / Recent Trades:** Dashboard history fetch used `limit=200` while the API caps at 100 — request failed with 422 and left both widgets empty. Now paginates at 100 until up to 200 closed trades load.
- **Active Option Desks:** Dashboard now loads `GET /positions/open` on mount (REST fallback when WS has not delivered positions yet) and maps broker `signedSize` through to the preview table.

---

## 2026-08-13 — Live max close→ST distance filter

### Added
- **Live `maxStDistancePct` (default 0.3, 0 = off):** Same close→ST distance gate as backtest — live entries and Market watch readiness require `|close − ST|/close×100` strictly below the threshold. Skips log to Updates.

---

## 2026-08-13 — Backtest max close→ST distance filter

### Added
- **Backtest `maxStDistancePct` (default 0.3, 0 = off):** After EMA/ST pullback geometry, skip entry when `|close − ST line| / close × 100` is not strictly below the threshold. Diagnostics count `skippedStDistance`.

---

## 2026-08-11 — Running trade Bias + estimated stop/target PnL

### Fixed
- **Running Bias:** Adopted / open trades refresh `stColour` from the live SuperTrend; Running cards also fall back to the session indicator so Bias is not shown as “—”.

### Added
- **Running estimates:** Each open trade card shows Open (est.), Est. loss (stop), and Est. profit (target) from entry vs live/stop/target premiums.

---

## 2026-08-11 — ST Options limit-fill recovery + naked short sync

### Fixed
- **False `limit_unfilled`:** Cancel HTTP 404 / positions lag no longer drops tracking immediately. Await polls fills + multi-try positions; `average_fill_price` counts as a fill; `pending_entry` stays until reconcile confirms empty (3 ticks and ≥~2.5 minutes).
- **Naked shorts:** While the engine is on, each tick adopts unprotected short options on the live underlying into ST Options and attaches broker SL/TP; open trades missing brackets get a retry attach.
- **Manual / existing brackets:** Attach discovers open Delta SL/TP legs first (and again if place fails) so already-protected positions are linked instead of soft-only “could not be attached”.

---

## 2026-08-10 — ST Options history cursor pagination + footer layout

### Added
- **Live History:** Cursor-based pagination on `GET /st-options/history` (`limit`, `cursor` → `trades`, `nextCursor`, `hasMore`) with a full closed-trade `summary`; History tab pages of **20** with **Load more**, a “Showing X of Y” strip, and a capped scroll region. If an older API still returns a full list, the UI windows it client-side so records are not dumped at once.

### Fixed
- **App footer:** Running no longer uses `min-h-[calc(100vh-…)]`; shell is viewport-locked (`h-dvh`) with scroll inside `main`, so the footer stays on-screen.

### Changed
- **Dashboard equity / recent trades:** Requests the latest 200 closed ST Options trades (`limit=200`) for the curve and recent list.

---

## 2026-08-09 — ST Options Updates height, margin skips, broker-flat PnL

### Fixed
- **Margin skips:** Delta `insufficient_margin` (and other order reject codes) show a clear Updates line with available / additional balance needed instead of “order could not be placed”.
- **Broker-flat sync:** When the short is gone on Delta but Mongo still shows open (manual square-off, liquidate, cancelled brackets), the engine closes the ST trade as `broker_flat` using cover fill price for PnL.
- **Exit PnL:** Bracket/peer exits prefer fills API / `average_fill_price` before theoretical stop/target; live cards use stored `contractValue` in client fallback PnL.

### Changed
- **Updates panel:** Grows into remaining viewport height on Live → Running (flex scroll region instead of `max-h-40`).

---

## 2026-08-08 — ST Options saved backtest selection stickiness

### Fixed
- **Saved runs picker:** Choosing an older saved backtest no longer snaps back to the most recent job when live WebSocket session snapshots re-publish `backtestJob`.

---

## 2026-08-07 — ST Options unprotected fill hardening

### Fixed
- **Unprotected orphan risk:** Limit entry is recorded as `pending_entry` as soon as the order is placed. Fill confirmation re-checks the order **and** the short broker position after cancel; if a position exists, the trade is promoted and **broker SL/TP are attached immediately**. Each engine tick reconciles leftover pending entries the same way so a mis-detect cannot leave a naked short.

### Changed
- **Running UI:** Pending entries show “confirming entry” until fill + protection are verified.

---

## 2026-08-07 — ST Options limit entry fill race

### Fixed
- **Limit entry / hedge fill:** After the fill poll window, cancel is followed by a re-fetch so a fill that races the cancel is still tracked (avoids “Setup skipped — limit entry did not fill” while the position is open on Delta). Fill detection no longer requires `average_fill_price` when size/status already show a fill; partial fills update lot size.

---

## 2026-08-07 — ST Options running positions full width

### Changed
- **Running positions:** Open ST Options cards use the full container width (stacked) instead of a two-column half-width grid.

---

## 2026-08-07 — Live hedge beside main + fixed hedge stop

### Added
- **Fixed hedge stop:** At hedge fill, freeze `hedgeStopPremium = hedgeEntry + (mainProfit$ + maxRisk) / (cv × lots)` (e.g. 400 + 200 + 75 → 675). Broker SL-only attached once (never amended). Soft monitor also flattens both when hedge mark reaches the stop.
- **Running card layout:** Main and hedge show side-by-side with hedge **Protect at**; combined pair PnL below.

---

## 2026-08-07 — Live hedge details on Running cards

### Fixed
- **Hedge details visible after open:** Saving live settings no longer restores a stale `active[]` (wiping hedge fields that WS just published). Running cards show a hedge block (symbol, qty, received, live, main/hedge/combined PnL) when `hedgeStatus` is open.

---

## 2026-08-07 — Live hedge % hot-toggle save fix

### Fixed
- **Live hedge % save:** Strategy settings no longer reset from 15s WS snapshots while the modal is open (edits were wiped before Save). While the strategy is on, Save patches only `pairHedgeDecayPct`.
- **Immediate hedge apply:** After a live config PATCH that changes `pairHedgeDecayPct`, the engine runs manage/open-hedge immediately (and each tick re-reads Mongo config) so opposite-leg hedges can open without waiting for the next poll when decay is already met.

---

## 2026-08-07 — ST Options live pair hedge

### Added
- **Live pair hedge:** `pairHedgeDecayPct` on live config (default **0** = off). When &gt; 0, after the main short melts that %, the engine limit-sells the same-strike opposite option (same lots). Editable while the strategy is running; if decay is already met, the hedge opens on the next manage tick.
- **Paired exits:** main target/stop/ST-flip/expiry/manual/force close also closes the hedge. Combined unrealized PnL of main + hedge ≤ **−maxRisk** flattens both (`max_loss`). Setting decay to 0 leaves an open hedge in place (no new hedges).

### Notes
- Live hedge is decay-only (no immediate/parity mode). Hedge legs have no broker brackets; the engine exits them with the main. History emits a sibling closed row (`legRole: hedge`, shared `pairId`) when a hedge existed.

---

## 2026-08-06 — ST Options backtest pair hedge

### Added
- **Pair hedge (backtest only):** Optional `pairHedgeEnabled` shorts the same-strike opposite option (PUT↔CALL) with the main leg.
  - **`immediate`:** both open together; favor exit when PE ≈ CE (`pair_parity`); main SL closes both.
  - **`on_decay`:** hedge opens after main melts `pairHedgeDecayPct` (default 40); both exit on main target/SL.
- Switch off → unchanged single-leg behavior. Ledger emits two rows sharing `pairId` when a hedge existed.

---

## 2026-08-06 — Dashboard equity performance wave redesign

### Changed
- **Equity Performance Wave:** Working **1W / 1M / All** range filters; smoothed curve with zero baseline, split green/red area, win/loss trade markers, crosshair tooltip (IST time, symbol, cum + trade P&L), and a stats strip (Total P&L, win rate, max drawdown, trades).

---

## 2026-08-06 — ST Options live limit entry + hard max-risk cap

### Changed
- **Live entry is a limit sell** at live mark/last − $1 (not market). Lots are sized from that limit price and the live `stopLossPct` preference.
- **Hard max-risk cap:** if one lot’s SL risk would exceed `maxRisk`, the setup is skipped (no forced 1-lot entry). Unfilled limits are cancelled and skipped.

### Notes
- A sell can still fill above the limit; SL/TP use the real fill (slight risk overshoot possible). Product default `stopLossPct` remains 105.

---

## 2026-08-03 — ST Options quantity display + skip after Target

### Added
- **Quantity on surfaces:** Running cards, History/Backtest trade table (header **Quantity**), and Dashboard Recent Trades show lot count (`lots`).
- **Backtest skip after Target** (`skipSetupsAfterTarget`, default **1**, `0` = off): after a **take_profit** exit on a side, skip the next N entry signals on that side (Long/Short independent). Independent of `oneTradePerFormation`.

### Changed
- Trade views always emit `lots` (default 1) for older docs missing the field.

---

## 2026-07-31 — ST Options live max-risk sizing

### Changed
- **Live Size → Max risk ($):** Live entries size lots with the same formula as backtest (`maxRisk` ÷ (premium × stopLossPct/100 × contractValue)). Config/API/UI use `maxRisk` instead of coin `quantity`.

---

## 2026-07-30 — ST Options backtest max-risk sizing

### Changed
- **Backtest Size → Max risk ($):** Lots are derived each entry from `maxRisk`, configured `stopLossPct`, entry premium, and contract value (`lots = floor(risk / (premium × SL%/100 × cv))`, min 1). Live still uses coin quantity.
- **Dynamic sizing uses % of base risk:** After N losses add `maxRisk × increase%` (cap at `maxRisk × maxRisk%`); after M profits subtract decrease%; then recompute lots from the new budget and that entry’s premium.

---

## 2026-07-30 — ST Options backtest strike modes + formation gate

### Added
- **Backtest strike selection modes** (mutually exclusive, live unchanged): `fixed` (OTM10…ATM…ITM10 with auto same-day before 05:30 IST / next-day after), `min_pct` (existing % waterfall), `supertrend` (ATM snapped to ST line), `min_abs` (absolute premium floor). Persisted on `st_options_backtest_config` / job body as `strikeSelectMode`, `strikeType`, `minPremiumAbs`.
- **One trade per SuperTrend formation** (`oneTradePerFormation`, default off): after any exit on a side, no re-entry on that side until `st_colour` changes (disables same-colour TP re-entry).

### Changed
- **Backtest gear UI:** Strike-mode dropdown with conditional inputs (no expiry select); formation toggle always shown in backtest settings.

---

## 2026-07-30 — ST Options Backtest Lab

### Added
- **Backtest persistence:** Per-user `st_options_backtest_config` and saved runs in `st_options_backtest_runs` (last ~50). APIs: `GET/PATCH /backtest/config`, `GET /backtest/runs`, `GET/DELETE /backtest/runs/{id}`. Completed jobs attach `runId`.
- **Backtest UI:** From/To stay outside (defaults **today−7 IST → today IST**); gear modal for settings; saved-runs picker; **Compare** modal (input diffs, overlapping trades, normalized % PnL, verdict) with CryptoBridge PDF download (`jspdf`).
- **Dynamic lot sizing (backtest only):** Optional consecutive-streak sizing (after N losses +lots up to max; after M profits −lots floored at initial). **Lots** column on trades.
- **Richer summary KPIs:** Total wins/losses, max winning/losing streak as `len(count)` (e.g. `4(2)`), average profit / average loss.

### Changed
- **Backtest performance:** Parallel Delta product + option candle fetches (semaphore), narrower option candle windows (not 120d warmup), bisect lookups — same strategy outcomes, much faster wall time.

---

## 2026-07-30 — ST Options breakeven trail + live UI polish

### Added
- **ST Options setting `breakevenDecayPct`:** Move stop to breakeven (entry premium) after this % of premium melt. Default **40**; **0 = off**. Wired in live config / start / backtest body and settings UI. Live amends broker SL when brackets are attached; backtest uses the same rule.

### Changed
- **ST Options Running:** Strategy card shows **Total PnL** from closed history.
- **ST Options Bias icons:** Replaced with clear up/down arrows (larger).
- **ST Options Updates:** Losing closes use warn (red); profit/loss result lines are bold.

---

## 2026-07-28 — ST Options live Market price + summary Long/Short

### Fixed
- **ST Options Market:** Header Market price uses live `/ws/live` spot ticks for the configured underlying (falls back to last 1H bar close only if WS spot is unavailable).
- **ST Options Bias icon:** Thicker stroke and larger size so Up/Down trend icons are readable.
- **ST Options summary:** Long / Short count closed history trades by direction (were stuck at 0 while flat because they counted only open positions).

---

## 2026-07-28 — ST Options header summary + Dashboard trades

### Changed
- **ST Options Live:** Removed Market snapshot card; header shows As of, Bias (SVG icon), and Market price. Running tab adds a compact live strategy summary (trades, open Long/Short, profit/loss counts, max/total P&L, loss-to-profit).
- **ST Options Bias:** Up/Down text replaced with trend SVG icons (header, Market watch, open cards, History table).
- **Dashboard:** Equity Performance Wave plots cumulative P&L from closed ST Options history. Asset allocation donut replaced by **Recent Trades** (square-off IST + PnL).

### Fixed
- **ST Options Updates:** Activity timestamps render in IST (no longer a raw UTC clock slice).
- **Dashboard Equity Wave:** Loads `GET /st-options/history` so the curve is no longer stuck empty.

---

## 2026-07-28 — Settings modal crash + gear icons

### Fixed
- **Workspace settings:** Restored missing `SettingsAccountsTab` import so opening Settings no longer throws `ReferenceError`.
- **Gear icons:** Header and ST Options settings buttons use a complete cog SVG path (paths were truncated and rendered blank).

---

## 2026-07-27 — Live WebSocket reconnect storm fix

### Fixed
- **`/ws/live` client:** Reconnects no longer schedule on intentional closes, effect cleanup, or auth `1008`; stale sockets are ignored. App ping/pong counts as liveness so quiet markets do not force reconnect churn.
- **`/ws/live` server:** Disconnect sets `connected=False` before cancelling writers; sends no-op after disconnect; drains/close AssertionErrors are treated as disconnect instead of ERROR spam.

---

## 2026-07-26 — ST Options live broker SL / TP brackets

### Added
- **ST Options live settings:** Stop loss (% premium rise) and Take profit (% premium melt) now use the same editable values as backtest (defaults 105 / 95) and apply to new entries.
- **Broker protection:** Every successful live option entry attaches Delta stop-loss and take-profit bracket orders and records their broker order IDs. Broker fills close the trade in history without a duplicate reduce order; attach failures retain soft mark/last monitoring.

### Changed
- **ST Options exits:** ST flip, manual stop, expiry close, settlement, and force-close paths cancel pending bracket legs before the strategy exits or closes its record.

### Fixed
- **Bracket cancel / reconcile races:** Cancel failures no longer wipe `stopOrderId` / `takeProfitOrderId`; already-filled legs record the broker exit instead of market-reducing; undiscoverable legs fall back to soft monitoring instead of leaving Mongo stuck `open`.

---

## 2026-07-26 — ST Options backtest: editable SL / TP %

### Added
- **ST Options backtest:** Settings now include **Stop loss (% premium rise)** (`stopLossPct`, default 105) and **Take profit (% premium melt)** (`takeProfitPct`, default 95). The backtest runs its SL/TP brackets from these inputs (`POST /st-options/backtest` accepts `stopLossPct` / `takeProfitPct`; echoed in result settings and `/meta` defaults).

---

## 2026-07-26 — ST Options OTM-first waterfall + expiry lifecycle

### Changed
- **ST Options entry:** Waterfall prefers furthest OTM across eligible expiries; same-day (T0) entries only at/before **10:30 IST**; ties go to next-day (T1).
- **ST Options exits:** Same-day opens force square-off at **17:15 IST**; past settlement auto-settles at intrinsic; re-entry allowed after expiry close.

### Added
- **Force close:** `POST /st-options/trades/{id}/force-close` marks stuck no-contract opens closed in Mongo (`force_closed`) without a broker reduce; leftover UI shows Force close after product-missing failures.

---

## 2026-07-25 — ST Options page tint clears header

### Fixed
- **ST Options Live:** Bias wash panel has top margin so it no longer sits flush against the nav.

---

## 2026-07-25 — Remove ST Options Market snapshot breathing glow

### Removed
- **ST Options Live:** Market snapshot no longer uses the breathing green/red glow; page-wide bias wash remains.

---

## 2026-07-25 — ST Options settings modal, bias copy, page tint

### Changed
- **ST Options Running:** Settings moved behind a gear → **Strategy settings** modal; **Advanced** requires a confirm warning (not recommended). Removed risk/concurrency footnote and the lonely empty “Strategy is on…” card.
- **ST Options Market watch:** Opposite side says **Not active while bias is down/up** instead of waiting for the opposite bias.
- **ST Options Live:** Soft page-wide green/red bias wash on Running.

---

## 2026-07-24 — ST Options plain-language Live UX + operator logs

### Changed
- **ST Options Live:** Running copy uses calm desk language (Strategy on/off, Market watch, Bias, Size, Minimum option price %, Protect at/Target). ST/EMA/T0–T1 jargon sits under **Advanced**. Activity feed shows plain `userMessage` only.
- **ST Options History / toasts:** Exit reasons map to Market flipped / Stop / Target / Closed manually; start/stop toasts match the same voice.

### Added
- **ST Options activity:** Dual fields — technical `message` (support) + plain `userMessage` (Live UI).
- **ST Options logging:** Structured `ST Options:` server logs on start/stop, new 1H bars, signals, opens, skips, and closes (grep for forensics; see [st-options-1h.md](./st-options-1h.md)).

---

## 2026-07-24 — ST Options live engine status panel

### Added
- **ST Options Live:** `status` on live/WS snapshot — phase, Long/Short readiness + reasons, next 1H close countdown, last tick, and rolling activity feed so Running stays informative while flat.

---

## 2026-07-24 — ST Options running empty-state copy

### Changed
- **ST Options Running:** When the engine is on with no opens, show “waiting for the next 1H entry” instead of a bare empty list (Start does not open a trade immediately).

---

## 2026-07-24 — ST Options leftover opens after Stop

### Fixed
- **ST Options WS:** Unstamped or older `st_options_session` payloads no longer overwrite stamped `config` / `active` / `indicator` (stops stale cards after Stop).
- **ST Options close:** Mongo marks a trade closed only after a successful broker reduce; Stop retries leftover opens once.

### Changed
- **ST Options Running:** When STOPPED with tracked opens, shows a leftover panel + **Close legs** (not a live Running look). Deploy alone does not auto-close prior opens — press Stop or Close legs.

---

## 2026-07-24 — ST Options T0/T1 expiry + start/stop Live

### Fixed
- **ST Options products:** `/v2/products` now filters with `expiry=YYYY-MM-DD` (was wrongly `expiry_date`, so far-dated contracts could be sold).
- **ST Options live/backtest:** Only products whose symbol expiry matches the requested T0/T1 day are cached; orders use `resolved.symbol` and refuse non-T0/T1 symbols.
- **ST Options Start/Stop UI:** Start applies settings + enable in one request (no PATCH race); WS session merge respects newer `config.updatedAt`.
- **ST Options Stop:** Flattens all open ST Options legs (`manual_stop`) before disabling the engine.

---

## 2026-07-24 — Fix ST Options breathing glow not loading

### Fixed
- **ST Options Live:** Breathing green/red indicator glow CSS now lives in loaded `index.css` (was in unused `styles.css`); glow wraps the card so Tailwind `shadow-sm` no longer hides it.

---

## 2026-07-24 — ST Options indicator breathing glow

### Changed
- **ST Options Live:** Indicator card ST-coloured shadow breathes gently; light theme uses a thicker glow than dark.

---

## 2026-07-24 — ST Options start-live Mongo conflict

### Fixed
- **ST Options `/start`:** Upsert no longer puts `enabled`/`updatedAt` in both `$set` and `$setOnInsert` (Mongo code 40 conflict).

---

## 2026-07-24 — Error toast uses rose accent

### Fixed
- **Workspace toast:** Error notifications use a rose left border (were always lime/green).

---

## 2026-07-24 — ST Options live ST colour tint

### Changed
- **ST Options Live:** Indicator card uses a soft green/red shadow from SuperTrend colour; Last bar time, SuperTrend, and EMA are mildly emphasized in the page subtitle.

---

## 2026-07-24 — ST Options backtest 0-trades fix + SL correction

### Fixed
- **ST Options backtest:** Prefetch option candles across **min→max** window spot ± ITM3 (was median ±3), and lazy-fetch missing waterfall symbols so spot drift no longer silently yields 0 opens.
- **ST Options SL:** Stop is **entry + 105% of entry** (= **2.05×** premium), not 1.05×.

### Added
- **ST Options backtest diagnostics:** `result.diagnostics` (`barsInWindow`, `entrySignals`, `opened`, `skippedNoContract`, `skippedNoPremium`); Backtest UI notes skips when 0 trades.

---

## 2026-07-24 — 1H SuperTrend Options Sell (ST Options)

### Added
- **ST Options:** New top-nav product for BTC/ETH 1H options selling — TradingView-parity SuperTrend(10,3) + EMA(10), Live (Running | History) + Backtest.
- **Rules:** Long sells PUT / Short sells CALL; T0→T1 ATM…ITM3 premium waterfall (min % of perp); exits on opposite ST close, entry+105% SL (2.05×), 95% melt TP; TP re-entry; concurrent Long+Short.
- **API / WS / Mongo:** `/api/st-options/*`, WS `st_options_session`, collections `st_options_config` / `st_options_trades`.
- **Docs:** [st-options-1h.md](./st-options-1h.md).

---

## 2026-06-30 — Execution: allow scheduled ITM sells

### Changed
- **Execution page:** Removed ITM immediate-execution warning; monitors always wait for the configured spot entry level, including in-the-money options.

---

## 2026-06-30 — Execution option live premiums

### Changed
- **Execution page:** Option search list shows live premium on the right of each symbol; selected option panel shows the chosen contract and its live premium. Backend subscribes returned option symbols to the live price feed.

---

## 2026-06-30 — Spot-triggered option execution engine

### Added
- **Execution page:** Standalone nav item for BTC/ETH option sell with spot entry trigger, spot stop-loss monitor, margin preview, and active monitor table.
- **Backend:** `ExecutionEngineService` (`spot_sl_monitors` Mongo collection), status flow `Pending Trigger` → `Order Placed` → `Order Filled` → `Squared Off`.
- **Safe Mode:** On spot feed disconnect while filled, places reduce-only option stop at premium +50%; cancels stop when feed reconnects.
- **API:** `GET/POST /api/execution/*`; WS `execution_monitor` on `/ws/live`.

---

## 2026-06-30 — Execution Terminal: deep backend cleanup

### Removed
- **Backend:** RWB, Move Straddle, Strike Advisor stacks — routers (`/api/rwb/*`, `/api/move-straddle/*`, `/api/strike-advisor/*`), services, candle cache, ML forecast, and strategy utils.
- **Market data:** Candlestick feed, funding-rate channel, and legacy `watchlist_items` Mongo reads removed; live prices only.
- **Dependencies:** `numpy`, `pandas`, `scikit-learn` dropped from backend requirements.
- **MongoDB:** Collections `rwb_sessions`, `candle_cache`, `candle_cache_coverage`, `strike_forecast_models`, `watchlist_items` dropped on startup.

### Changed
- **WebSocket `/ws/live`:** Topics limited to snapshot, price, margin, positions, ping/pong.

---

## 2026-06-30 — Execution Terminal: remove SPS / ST Perp strategy stack

### Removed
- **Frontend:** Strategy pages (SPS, ST Perp, Wick Break, Move Straddle, Strike Advisor). Nav is **Dashboard** and **Active Positions** only; terminal state is `{ watchList, fsmEngines }`.
- **Backend:** `sps_*` and `st_perp_*` services, routers (`/api/sps/*`, `/api/st-perp/*`), `sps_indicators`, `sps_option_resolver`.
- **MongoDB:** Collections `sps_setups`, `sps_trades`, `st_perp_trades`, `st_perp_setups` dropped on startup.

---

## 2026-06-30 — ST Perp: bracket exits + ledger alignment

### Fixed
- **ST Perp exits:** Runner and session-end fills use bracket stop when 90m close would be worse than SL (stops losses exceeding sized max risk from candle close).
- **ST Perp bar ledger:** Signals match simulation (`ENTER`, `IN TRADE`, `SKIP sizing`, `ARM`) so chart markers align with executed trades.

---

## 2026-06-30 — ST Perp: SuperTrend + exit settings, sizing fix

### Added
- **ST Perp backtest & live:** Configurable SuperTrend period/multiplier, min SL distance, partial exit percentages, R targets, and ST-flip runner toggle.

### Fixed
- **ST Perp sizing:** Entries skip when one contract would risk more than `maxRiskAmount` (previously forced 1 contract — e.g. $10 risk with a wide stop could lose ~$30 at SL).

---

## 2026-06-30 — ST Perp futures strategy

### Added
- **ST Perp:** New nav product for BTC/ETH perp futures — arm on 90m ST flip, mark ST on 1m wick tap, enter on 1m close confirm with risk-based sizing and min $1 stop distance. Exits: 30% at 3R, 30% at 10R, 40% on opposite 90m ST flip close. Live Engine, Trade History, and Backtest Lab mirror SPS workspace; `st_perp_session` WebSocket; Mongo `st_perp_setups` / `st_perp_trades`.

---

## 2026-06-30 — SPS entry: 1m SuperTrend line tap

### Changed
- **SPS entry:** Replaced EMA/blend clearance with **1m intrabar ST line tap** while armed after flip. PUT when `low <=` prior closed 90m ST; CALL when `high >=` prior ST. Option entry premium from **1m option candles at tap time**; exits unchanged on 15m brackets. Backtest fetches 1m spot + 1m entry options; bar ledger shows `stLineForTap`, `stTapped`, `tapTimeIst`. Live runner scans 1m perp each tick while armed. Removed `emaStBlend` from UI/API.

---

## 2026-07-13 — SPS ITM strike waterfall + 1% premium gate

### Changed
- **SPS strike resolution:** ITM-only grid snap from ST (put ceil / call floor; ETH step 20, BTC step 200), up to +2 ITM steps, min premium **1% of spot**; **T+2** primary, **T+3** fallback. Backtest prefetch all waterfall symbols; bar ledger shows `no contract (1% spot)` when clearance passes but resolve fails.

---

## 2026-07-13 — SPS backtest live WebSocket progress and trace

### Fixed
- **SPS backtest:** `POST /api/sps/backtest` returns immediately (no longer awaits indicator snapshot fetch). Progress stages and trace lines stream on `sps_session` WebSocket (`backtestJob`) during the job; completion still pushes full result. Simulation runs in a worker thread so polls and WS stay responsive.

---

## 2026-07-13 — SPS armed pullback entry + configurable EMA/ST blend

### Changed
- **SPS entry:** ST flip now **arms** a watch direction; every closed 90m bar while SuperTrend color is unchanged re-evaluates EMA side (PUT below EMA, CALL above) and blend threshold toward ST using **current** EMA/ST. Default blend **0.5** (was 0.75 flip-only). User setting `emaStBlend` (0–1) on live start and backtest. Bar ledger shows threshold and armed/skip on all green/red bars.

---

## 2026-07-13 — WebSocket keepalive ping error fix

### Fixed
- **Backend:** Uvicorn now starts via `python -m cryptobridge.server` with `ws_ping_interval=None` so protocol-level keepalive pings do not race with `/ws/live` writes (fixes `keepalive ping failed` AssertionError on Windows). Delta public/private WS sends are serialized with a lock; app-level ping/pong on `/ws/live` unchanged.

---

## 2026-07-13 — SuperTrend HL2 TradingView default parity

### Fixed
- **SPS indicators:** SuperTrend pivot switched from HLC3 to **HL2** (`(high+low)/2`) to match built-in TradingView SuperTrend (8, 3). Direction flip restored to Pine state-machine logic; first ATR bar initializes red on upper band. Bar ledger adds `hl2`, `stUpper`, `stLower` columns. Golden-bar regression test locks ETH 2026-06-03 01:00 IST ST line to **1975.86**.

---

## 2026-07-13 — SuperTrend TV parity refactor

### Changed
- **SPS indicators:** `calculate_sps_supertrend` (alias `compute_supertrend_tv`) uses explicit ternary band pinning, direction flip only on close cross vs **previous** pinned bands, and line tracking on the **current** lower/upper band (TradingView default). `SuperTrendPoint` now includes `upper_band` / `lower_band`. Backtest trace and live snapshot log the last 5 bars for TV comparison.

---

## 2026-07-13 — SPS single-leg entry with EMA/ST blend clearance

### Changed
- **SPS entry:** Removed two-leg scaling. Full quantity on one entry: green ST flip → short put when close **<** `EMA − 0.75×(EMA−ST)`; red flip → short call when close **>** `EMA + 0.75×(ST−EMA)`. Strike = nearest listed **ST line** strike; expiry **T+2** only. Bar ledger shows `entryThreshold` column.

---

## 2026-07-13 — SPS backtest 90m bar ledger

### Added
- **SPS backtest:** Response includes `bars90m[]` — every closed 90m candle in the window with OHLC, HLC3, EMA20, SuperTrend line/direction/flip, and signal/skip reason on ST flips. Paginated **90m Bar Ledger** table in Backtest Lab.

---

## 2026-07-13 — SPS EMA/SuperTrend TradingView parity fix

### Fixed
- **SPS indicators:** SuperTrend band pinning now compares against the **previous** bar's final bands (Pine `ta.supertrend` parity). EMA(20) and SuperTrend(8,3) HLC3 are computed on **120 days** of 90m history before the backtest/live window so values match TradingView instead of cold-starting on the selected date range.

---

## 2026-07-13 — SPS backtest trace log (server + UI)

### Added
- **SPS backtest:** Full trace log through prefetch, symbol resolution, simulation, and every ST flip / skip / leg1 / leg2 / exit. Lines stream live on the job (`traceLog`) and appear in the Backtest Lab UI. Python `logging` mirrors the same messages. Diagnostics summary shows flip vs trade counts.

---

## 2026-07-13 — SPS backtest symbol resolution no longer hangs

### Fixed
- **SPS backtest:** Strike-ladder lookups for expired Delta products now run in parallel (4 concurrent) with per-request timeout instead of blocking sequentially on every signal bar. Progress shows `Building option symbol list (n/m)…` during ladder prefetch.

---

## 2026-07-13 — SPS backtest job polling and prefetch fix

### Fixed
- **SPS backtest:** Prefetch option candles from waterfall symbols before resolve (premiums were never available without cached candles). Cap expired-product API pagination. Poll lightweight `GET /sps/backtest/job` with live progress text instead of heavy `/sps/live`. Job state publishes fresh objects on completion for WebSocket clients.

---

## 2026-07-13 — SPS UI aligned to Calendar Spread workspace

### Changed
- **SPS UI:** Live Engine, Trade History, and Backtest Lab rebuilt on Calendar Spread workspace chrome — Settings/Start/Stop Engine, Leg Monitor, equity curve, performance snapshot, paginated ledger, expandable history runs.

---

## 2026-07-13 — SPS bracket exit pricing

### Fixed
- **SPS SL/TP:** Backtest `MANAGE_TRADE` now uses 15m option **high/low** bracket fills at exact **1.5×** / **0.1×** entry (not spot-bar close). Live take-profit records exact target premium, not live mark.

---

## 2026-07-13 — SPS EMA clearance and per-direction concurrency

### Changed
- **SPS leg1 filter:** Close must be at least **0.3%** beyond EMA20 (below for puts, above for calls).
- **SPS concurrency:** One open trade per direction; same-direction flips ignored while active; opposite direction may still enter.

---

## 2026-07-13 — SPS strike resolution, premium exits, async backtest

### Changed
- **SPS strike/expiry:** Listed Delta ladder + ITM waterfall (`sps_option_resolver.py`); maturity-aware strike steps (D1/D2 per Delta India guide); expiry +2d with +1d/+3d fallback. Setups skip only after all contract attempts fail.
- **SPS exits:** Premium-only SL (1.5×) and TP (0.1×) on 15m option candles; removed spot 4R/20R partial-book logic and UI fields.
- **SPS backtest:** Async `POST /api/sps/backtest` with `backtestJob` on `sps_session` WS; trade rows include `stLineValue`, `ema20`, `leg2StLineValue`, `leg2Ema20`; `diagnostics` block.
- **SPS UI:** Move Straddle workspace chrome; coin quantity with lots hint.

### Fixed
- **SPS backtest under-trading:** No longer drops valid ST flips as `skip_leg1_no_premium` when rounded strike is unlisted.

---

## 2026-06-30 — SuperTrend Pullback Scaler (SPS)

### Added
- **SPS product:** Replaces Directional Options Selling on the **ST Pullback** nav slot. 90m IST bars, TV-parity EMA(20) + SuperTrend(8,3) on HLC3, two-leg scaling (50% ST flip + 50% ST pullback), strike from ST line, expiry +2 days, 4R/20R management, live + backtest UI, drift diagnostics.
- **API:** `GET/POST /api/sps/*`, `POST /api/sps/backtest/run`; WebSocket `type: sps_session`.
- **Mongo:** `sps_setups`, `sps_trades`.
- **Docs:** [supertrend-pullback-scaler.md](./supertrend-pullback-scaler.md).

### Removed
- **Directional Options Selling:** Live engine, backtest lab, `/api/directional-options/*`, Dir. Options nav. Shared helpers migrated to `options_trade_helpers.py`. Legacy `directional_options_*` Mongo collections preserved read-only.

---

## 2026-07-12 — Wick Break configurable timeframe

### Added
- **Wick Break:** **Timeframe** selector (`1m`, `5m`, `15m`) on live start and backtest modals. Engine fetches and simulates on the chosen resolution; session status and backtest stats show active timeframe.

---

## 2026-07-12 — Wick Break pattern direction fix

### Fixed
- **Wick Break:** Corrected `signal_side()` mapping — **shooting star → LONG (BUY)**, **hammer → SHORT (SELL)** — matching pattern bias in `candle_patterns.py` and Directional Options. Previously inverted (classic breakout TA mapping).

---

## 2026-07-12 — Wick Break native Delta 1h swing data

### Changed
- **Wick Break H1 swing filter:** Fetches Delta native **`1h`** REST candles instead of aggregating 15m bars. Bucket alignment uses Delta chart opens (:30 IST / UTC hour boundaries) via `delta_h1_bucket_open()`.

---

## 2026-07-12 — Wick Break H1 unmitigated swing filter

### Added
- **Wick Break:** Optional **H1 unmitigated swing filter** (`useSwingFilter`, `swingProximityBufferPct` default **0.05%**). After RWB pattern + min SL checks, shooting-star highs must sit near an unmitigated H1 swing high; hammer lows near swing low; otherwise `no_swing_proximity`. H1 levels pre-calculated from 15m candles before the 1m loop.
- **UI:** **Structural Confluence** section in live start and backtest modals; session status shows filter state; ledger columns **Swing Level**, **Dist to Level %**, **Skip Reason**; skipped-signals table in backtest results.
- **Trade metadata:** `swingLevel` and `distToLevelPct` on taken trades and skipped signals for analysis.

---

## 2026-07-12 — Wick Break strategy documentation

### Changed
- **Docs:** [rejection-wick-breakout.md](./rejection-wick-breakout.md) expanded to full strategy reference (pattern geometry, FSM, sizing, fees, API, Mongo, live vs backtest, FAQ). [FEATURES.md](./FEATURES.md) §9 links to it as source of truth.

---

## 2026-07-12 — Wick Break minimum SL distance filter

### Added
- **Wick Break:** Reject setups when entry-to-stop distance is below **min SL distance** (default **50** price points). Configurable in backtest and live start modals (`minSlDistance`). Live activity logs `sl_distance_too_small`.

---

## 2026-07-12 — Wick Break backtest ledger PnL and quantity

### Fixed
- **Wick Break backtest:** Trade ledger **Result (R)** column restored to **net PnL** (after fees). **Quantity** column shows risk-sized entry contracts (`initialSize` from max-risk sizing); expanded row also shows coin equivalent when `contract_value` < 1.

---

## 2026-07-12 — Vanilla Wick Break restore (1m perps)

### Added
- **Wick Break product:** Restored `/api/rwb/*` live sessions + sync backtest on **1m perp futures** (BTCUSD, ETHUSD). Vanilla hammer/shooting-star geometry with C3 structure; hammer → long, shooting star → short; no EMA/confluence/swing filters.
- **Trade management:** Configurable `partialBookR` (default 4) and `partialBookPct` (default 50%); breakeven stop after partial; final target 20R; 5-bar entry fill timeout.
- **UI:** **Wick Break** nav page (Live / History / Backtest) with simplified settings and trade ledger (entry time, instrument, direction, entry/exit, result R).
- **Backend:** `rwb_engine.py`, `rwb_service.py`, `rwb_execution.py`, `rwb_backtest_service.py`, `utils/candle_levels.py`; 1m data via `CandleCacheService`.

---

## 2026-07-12 — Directional options swing filter + partial book

### Changed
- **Partial-book ladder:** Configurable `partialBookR` (default **4.0**) and `partialBookPct` (default **0.50**). When underlying reaches partial R, close that fraction of the option leg and move remaining stop to breakeven. Stored on `directional_options_trades` and backtest ledger metadata.
- **Directional options RWB:** Optional **H1 unmitigated swing filter** (`useSwingFilter`, `swingProximityBufferPct` default **0.05%**). Shooting-star highs must sit near an unmitigated H1 swing high; hammer lows near swing low; otherwise `no_swing_proximity`. Backtest ledger adds `swingLevel`, `distToLevelPct`, and `skipReason`.
- **Skip diagnostics:** `pattern_failed`, `no_swing_proximity`, `already_evaluated`.
- **Structure:** C3 must be the explicit structural extreme in hammer/shooting-star validation.
- **Toolkit:** `utils/market_structure.py` with `calculate_unmitigated_levels()` and IST-aligned H1 aggregation from 15m candles.

---

## 2026-06-30 — RWB confluence scoring (MACD teardown)

### Changed
- **FSM:** Replaced MACD divergence + pin bar with **Rejection Wick Breakout (RWB)** hammer/shooting-star geometry (C3/C2/C1 structure unchanged). Shooting star → short put; hammer → short call.
- **Confluence:** Volume (>1.2× 20-bar avg), 200 EMA trend alignment, and ATR-14 range gate each add 1 point (0–3). `minConfluenceScore` (0–3) controls trade acceptance; sub-threshold setups skip with `low_confluence_score`.
- **Toolkit:** `utils/candle_patterns.py`, `utils/rwb_confluence.py`, `utils/rwb_signal_series.py`; `ema_200`, `atr_14`, `avg_volume_20` precomputed before backtest loop.
- **API / Mongo / UI:** Replaced `macdFast` / `macdSlow` / `macdSignal` with `minConfluenceScore`. Backtest Lab and Live Engine use a confluence slider/dropdown. Trade ledger adds **Confluence Score** and **Skip Reason** columns; diagnostics show pattern + score breakdown.

---

## 2026-06-30 — MACD divergence + pin-bar strategy (BB teardown)

### Changed
- **FSM:** Removed all Bollinger Band entry logic (clearance, geometric separation, exhaustion filters). Entries now require **MACD divergence** (bullish → short put, bearish → short call) plus a **pin bar** on the last closed 90m candle.
- **Toolkit:** Added `detect_macd_divergence()` in `utils/macd.py` — scans the last 20 bars for price/MACD divergence at local extrema.
- **Skip log:** `no_divergence_detected`, `no_rejection_wick`, `already_evaluated`.
- **API / Mongo / UI:** Replaced `bbLength`, `bbMult`, `bbClearancePct` (and momentum filter fields) with `macdFast` (12), `macdSlow` (26), `macdSignal` (9). Live Engine and Backtest Lab show **Strategy parameters** panel; backtest returns `macdBars` and updated signal diagnostics.

---

## 2026-06-30 — Strategy revival: geometric separation + optional momentum

### Changed
- **FSM:** Replaced mandatory blow-off exhaustion AND-gate with **geometric separation** as the primary entry filter. **Put:** `close <= lower × long_mult` (default 0.2% pierce) and body separated (`max(open, close) > lower_band`). **Call:** `close >= upper × short_mult` and body separated (`min(open, close) < upper_band`). Parabolic spike (`relativeRangeMultiplier`, default **1.5**) and rejection wick (`rejectionWickRatio`, default **0.6**) are **optional** filters (`requireVolatilitySpike`, `requireRejectionWick`; default **off**).
- **Skip log:** Ordered `skipReason` precedence for diagnostics — `price_inside_bands` → `body_overlaps_band` → `volatility_spike_failed` → `rejection_wick_failed` (latter two only when optional filters enabled). Replaces `insufficient_exhaustion` and clearance-specific codes.
- **API / Mongo / UI:** Removed `bodyOutsideThreshold`. Added `requireVolatilitySpike` and `requireRejectionWick` on live start, backtest, saved configs, and setup documents. Live Engine and Backtest Lab expose checkboxes **Only High Volatility Spikes** and **Only High Conviction Rejections**. Backtest diagnostics add **Put pierce**, **Call pierce**, and **Geom** columns.

---

## 2026-06-30 — Blow-off exhaustion trap filter

### Changed
- **FSM:** Replaced simple BB breakout entries with **blow-off exhaustion** gates — parabolic range spike (`relativeRangeMultiplier`, default **1.5**) plus rejection wick (`rejectionWickRatio`, default **0.6**) required in addition to band clearance. Call: upper wick rejection + `close > upper_band`; put: lower wick rejection + `close < lower_band`. Band touches without exhaustion log `insufficient_exhaustion`.
- **API / Mongo / UI:** `relativeRangeMultiplier` and `rejectionWickRatio` on live start, backtest, saved configs, and setup documents. Backtest **Signal diagnostics** table adds **Spike** and **Rejection** columns (green Y / red N when band active).

---

## 2026-06-30 — Body-Outside high-conviction signal filter

### Changed
- **FSM:** Replaced prior-candle-inside-band trap gate and red/green candle shape requirement with **Body-Outside** strength (`bodyOutsideThreshold`, default **0.75**). Shape passes when **pin bar** OR body-outside ratio ≥ threshold; candle color is diagnostic only. New `skipReason`: `insufficient_candle_strength` when clearance passes but both pin and body-outside fail. Removed `previous_candle_outside_band`, `put_shape_failed`, `call_shape_failed`.
- **API / Mongo / UI:** `bodyOutsideThreshold` on live start, backtest, saved configs, and setup documents (parity with `bbClearancePct`). Live Engine and Backtest Lab expose **Body outside** input (unitless ratio, 0.75 = 75% of body past band).

---

## 2026-06-30 — Directional Options backtest trade time (IST)

### Added
- **Backtest:** Each trade in `trades[]` now includes `entryTimeIst` and `exitTimeIst` (`YYYY-MM-DD HH:MM` IST). Backtest Lab trade ledger shows **Time (IST)** column.

---

## 2026-06-30 — Instrument-specific waterfall strike steps

### Fixed
- **Premium waterfall:** ETH strike increment corrected from 50 to **10** (`get_strike_step`). BTC remains **200**. Waterfall ITM probing in live and backtest now always uses `get_strike_step(underlying)` instead of a shared wrong default.

---

## 2026-06-30 — Replace volatility exhaustion with previous-candle trap filter

### Changed
- **FSM:** Removed opposite-band slope gate (`volatility_expanding`). Put/call signals now require the prior 90m bar to have closed inside the band (`previous_candle_outside_band` when it did not).

---

## 2026-06-30 — Directional Options volatility exhaustion filter

### Added
- **FSM:** Opposite-band slope gate — put signals require upper band flat/down (`upper_band[i] <= upper_band[i-1]`); call signals require lower band flat/up (`lower_band[i] >= lower_band[i-1]`). Setups that pass clearance + shape but fail the slope check log `volatility_expanding` in backtest signal diagnostics and `signalsSkippedByReason`.

---

## 2026-07-12 — Directional Options strategy reference (full spec)

### Changed
- **Strategy doc:** [directional-options-strategy.md](./directional-options-strategy.md) expanded to full business + technical reference — glossary, worked examples, replace-vs-skip, bracket SL/TP, reason-code index, live/backtest parity, Mongo/API, FAQ.

---

## 2026-07-12 — Fix keep-existing backtest still replacing legs

### Fixed
- **Backtest / live:** `replaceSameDirection: false` was ignored because `False or …` treated explicit `false` as missing and defaulted to replace mode. Keep-existing backtests could still show `replaced` exits.

---

## 2026-07-12 — Same-direction replace vs skip option

### Changed
- **Directional Options:** `replaceSameDirection: false` now **keeps the existing leg and skips** the new same-direction signal (no second leg). Previously it incorrectly opened a stacked leg.

### Added
- **Directional Options:** `replaceSameDirection` on live setup and backtest (default **replace**). Backtest Lab and Live Engine **Same-direction signal** dropdown: *Replace existing leg* or *Keep existing (skip new signal)*.

---

## 2026-07-12 — Same-direction replace vs keep-both option

### Added
- **Directional Options:** `replaceSameDirection` on live setup and backtest (default **replace**). Set `false` to keep an existing put/call leg running when a new same-direction signal fires; both legs get independent SL/TP. Backtest Lab and Live Engine expose a **Same-direction signal** dropdown.

---

## 2026-07-12 — Directional Options bracket SL/TP exit pricing

### Fixed
- **Backtest SL/TP:** Option 15m candle **high/low** now trigger bracket exits; fill price is the exact **stopPremium** or **targetPremium** (e.g. entry 31 → SL exit **46.5**, not candle close 81). Live trade close records the same bracket prices on SL/TP.

---

## 2026-07-12 — Directional Options waterfall ITM direction

### Fixed
- **Premium waterfall:** Strike ladder now steps **toward spot** (more ITM) after the wick strike — calls try lower strikes (e.g. 1720 → 1710 → 1700); puts try higher strikes. Matches documented CE/PE premium procedure; see [directional-options-strategy.md](./directional-options-strategy.md) §7.2.1 worked example.

---

## 2026-07-12 — Directional Options strategy reference doc

### Added
- **Strategy doc:** [directional-options-strategy.md](./directional-options-strategy.md) — complete BB FSM spec (90m bars, BB math, signals, waterfall, live/backtest, sizing, diagnostics).

---

### Added
- **Signal diagnostics:** Backtest results include `signalDiagnostics[]` (per 90m bar: BB checks, FSM outcome, waterfall execution/skip reason), `aggregateStats` (buckets formed/dropped), and `signalsSkippedByReason` summary. Backtest Lab has a collapsible **Signal diagnostics** table.
- **Configurable thresholds:** `bbClearancePct` (default 0.2) and `minPremiumPct` (BTC 1.2 / ETH 1.5) on backtest and live setup forms, API, and Mongo config.

### Fixed
- **15m→90m aggregation:** Slot-based grouping accepts open- or close-stamped 15m candles; boundary close candle at bucket end is attributed to the prior bucket.
- **Backtest timing:** Entry premium lookup and expiry date use IST bar-close time (not bucket open); backtest fetch window padded ±1 IST day to avoid edge clipping.

### Changed
- **Live Engine:** BB clearance % and min premium % are editable on Start (no longer read-only).

### Fixed
- **Bollinger bands:** BB now uses Pine-exact SMA + population stdev (TradingView defaults: length 20, mult 2, SMA, close source) and tick-aligned rounding ($0.01 for BTC/ETH perp). `bbRaw` fields preserve full precision for chart comparison.
- **Contract quantity:** Backtest and live `quantity` is underlying coin amount (`1` = 1 BTC → 1000 lots, `1` = 1 ETH → 100 lots).

---

## 2026-07-11 — Directional Options 90m IST bucket alignment

### Fixed
- **90m bar timing:** Live and backtest now aggregate six `15m` candles into Delta's IST-phased 90m buckets (opens at 01:00, 02:30, 04:00, …, 23:30 IST) instead of naive consecutive grouping from UTC midnight.

---

## 2026-07-11 — Directional Options backtest + tabbed UI

### Added
- **Backtest Lab:** `POST /api/directional-options/backtest` runs async BB FSM simulation on aggregated 90m bars with historical option premiums; equity curve, stats, and paginated trade ledger on the **Backtest Lab** tab.
- **Tabbed page:** `/directional-options` now has **Backtest Lab | Live Engine | Trade History** (Calendar Spread parity). Live tab retains chart-free bento terminal; history lists `directional_options_trades` from Mongo.
- **Backtest config:** Per-user form persistence in `directional_options_backtest_config` via `GET` / `PUT` `/api/directional-options/backtest/config` (also localStorage cache).
- **WebSocket:** `directional_options` payload includes `backtestJob` for background backtest completion without polling-only UX.

### Changed
- **REST:** `GET /api/directional-options/live` and `GET /active` return full live payload including `backtestJob`, `setups`, and `active`.

---

## 2026-07-11 — Directional Options BB FSM (replaces Calendar + HA)

### Added
- **Directional Options Selling FSM:** Live 90m Bollinger-band engine (`ddof=0`), execution waterfall, SL/TP, and conflict rules at `/directional-options`. REST `POST/GET /api/directional-options/*`; WebSocket `type: directional_options` with premium flash direction.
- **Shared utils:** `options_market.py`, `bollinger.py`, `candle_aggregate.py`, `strike_grid.py`; backend tests for BB, FSM, service, and live order sides.

### Removed
- **Calendar Spread** and **Reverse Calendar Spread** — full backend/frontend stacks, payoff auto-detection, and Strike Advisor “Apply to Calendar”.
- **HA Directional Options** backtest page and service.
- **Breaking:** In-app management for open calendar/reverse trades ends after deploy — close manually on Delta before release. Legacy Mongo collections are orphaned (no migration v1).

### Changed
- **Docs:** Confirmed Delta has no native `90m` OHLC resolution (official enum stops at `1h`/`2h`/…); documented 15m→90m aggregation rationale in `FEATURES.md` §9 and `delta-api-capabilities.md`.
- **Strike Advisor:** Forecast-only; uses `strike_grid_for_spot` via `DeltaRestClient` (no calendar service dependency).
- **Active Positions payoff:** Generic multi-leg curve only (no calendar/reverse tent).
- **Dashboard:** No longer loads calendar history for equity widget.

---

## 2026-07-11 — Reverse Calendar Spread production hardening

### Fixed
- **Live WebSocket:** `/ws/live` now subscribes to `reverse_calendar_spread_service`, attaches symbols, pushes initial `reverse_calendar_spread` payload, and forwards `topic: reverse_calendar` updates (PnL and backtest jobs without REST polling).
- **Strike selection:** `spread_max_profit_at_sell_expiry` infers IV from the far short premium (`sellEntry`); backtest and live candidate pick use risk-adjusted scoring per design §5.
- **Active Positions:** `detectReverseCalendarSpreadRows` + reverse payoff curve for short-far / long-near pairs.

### Changed
- **Ops:** Live logs use `[reverse-calendar-live]` prefix; `(accountId, status)` index on trades; UI copy clarifies near-long / far-short; payoff chart marks valley (min at strike).
- **Tests / docs:** Expanded helper, backtest, and live tests; full `FEATURES.md` §11c inventory; `FRONTEND_SMOKE.md` QA steps; design doc marked production-ready.

---

## 2026-07-11 — Reverse Calendar Spread

### Added
- **Reverse Calendar Spread:** Dedicated Backtest, Live, and History experience for long-near/short-far same-strike option pairs. The strategy has isolated REST routes, WebSocket state, collections, live-engine lifecycle, and a reverse payoff model.
- **Safety:** Near-expiry exit closes both legs together; live order paths preserve the existing paired-order recovery and broker reconciliation protections.
- **Docs:** Added [reverse-calendar-spread.md](./reverse-calendar-spread.md) and linked it from the complete feature reference.

---

---

---

---

---

---

---

---

---

## 2026-07-08 — Heikin Ashi Directional Options (replaces Covered Call)

### Added
- **HA Dir. Options:** Backtest engine `HADirectionalOptionsSeller` — dual-array HA signals + real OHLC execution; short OTM puts/calls, risk-based sizing, hard spot stops. API `POST /api/ha-directional/backtest`, WS `ha_directional_options`, Backtest Lab UI.

### Removed
- **Covered Call:** Deprecated perp + rolling ATM call backtest (`DeltaCoveredCallBacktester`, `/api/covered-call/*`, `CoveredCallPage`).

---

### Fixed
- **Covered Call backtest:** Quantity is in **lots** (1 lot = 0.001 BTC / 0.01 ETH perp notional + 1 CE contract). Fixes perp PnL being ~1000× the call leg when `quantityUnit` was `BTC`.

---

## 2026-07-08 — HA Directional noise filters (EMA/ATR/cooldown)

### Changed
- **HA Dir. Options:** Default bar resolution is now **15m**; entries add EMA(50) trend alignment on real closes, an ATR(14)-based minimum real body-size filter on the trigger candle, and a `cooldownBars` (default `4`) flat period after exits to reduce chop-driven overtrading.

---

## 2026-07-08 — Covered Call backtest engine

### Added
- **Covered Call:** Full-stack historical backtest — long BTC/ETH perpetual (never closed) + rolling short ATM calls with decay take-profit and 17:00 IST cutoff rolls. Backend `DeltaCoveredCallBacktester`, `POST /api/covered-call/backtest`, WebSocket `covered_call`, Backtest Lab UI and nav tab.

---

### Added
- **Cold-start (stopped engine):** Backend bootstraps symbol subscriptions and private WS routing for **all users with open trades**, not only when `enabled: true` — open positions stay managed after restart without opening the Live tab.
- **Smart `closing` recovery:** Stuck `closing` trades (>2 min) finalize as `closed` when broker legs are flat; revert to `open` only when legs remain open; `needsReconcile` when broker state is unknown.
- **Full-close rollback:** Buy-leg failure after sell close attempts compensating reopen (mirrors partial-close path); sets `needsReconcile` and blocks further auto-exits.
- **Closing visibility:** Live payload and History show `closing` positions with a “Closing…” badge until the DB records `closed`.
- **Dynamic-qty retry:** Failed `_on_live_trade_closed` persists `dynamicQtyPending`; scheduler retries streak/lots advance on the next tick.
- **Periodic entry reconcile:** Scheduler re-syncs broker entry prices for open `live_order` trades every 30 minutes.
- **Atomic deploy claim:** `lastDeployDay` set via `find_one_and_update` to reduce same-day double-deploy races.

### Fixed
- **Auto-exit guard:** Trades with `needsReconcile` skip scheduler, tick, and private-WS exit paths until manually cleared.
- **Single-leg marks:** Tick path uses stored marks and single-leg `leg_pnl` fallback when one option delists (e.g. after sell-leg expiry).
- **Flat-close PnL:** `runningPnl` used for all skip-live-order closes when broker is confirmed flat (not only `broker_flat` exit reason).

### Changed
- **Live UI:** Per-position reconcile badge; closing state on multi-spread tabs.

---

## 2026-07-07 — Calendar Spread live gap fixes (post-audit)

### Added
- **Live settings:** **Reset L/W streaks** button clears loss/profit streak counters without changing target deploy size (`resetDynamicQuantityStreaks` on `PATCH /calendar-spread/live/config`).
- **Cold-start bootstrap:** `resume_enabled_live` registers symbols + private WS accounts for enabled users with open trades after backend restart.
- **Investigation logging:** Expanded `[calendar-live]` logs for deploy, open/close lifecycle, broker orders, config patches, bootstrap, and recovery.

### Fixed
- **Stuck `closing`:** Trades left in `closing` >2 minutes revert to `open` on startup and each scheduler tick.
- **Shared legs:** Loss-streak scale-up skipped when broker legs overlap another open run (mirrors scale-down policy).
- **`broker_flat` PnL:** Uses last stored `runningPnl` instead of mark/entry fallback when legs are already flat.
- **Partial close:** Buy-leg failure after sell partial close attempts compensating reopen; sets `needsReconcile` + `brokerSyncWarning` on failure.
- **Private WS:** Single-leg flat updates marks/PnL from the remaining leg.
- **Entry reconcile:** Uses per-trade `accountId` credentials, not only the currently selected account.
- **Deploy safety:** Rolls back broker entry orders if DB insert fails after live placement.

### Changed
- **Live UI:** Scale-blocked (shared leg) warning on open positions; broker sync warning banner when reconcile is needed.

---

## 2026-07-07 — Calendar Spread live safety and quantity audit fixes

### Fixed
- **Live close:** Atomic `open` → `closing` guard prevents duplicate broker reduce orders on concurrent exit paths; missing broker legs abort close and revert claim.
- **Scale-down:** DB lots update only after confirmed partial broker close; shared-leg spreads skip profit-streak scale-down when symbols overlap another open run.
- **Scale-up:** Live scale-up rolls back sell leg on buy failure; blended `sellEntry`/`buyEntry` after fill-weighted scale-up.
- **Dynamic quantity:** Streak counters reset only when `currentLots` actually changes; `currentLots` clamped to max on load and when max is lowered; per-user lock on streak updates; `lastBumpLossStreak` cleared on profit decrease.

### Changed
- **Live / History UI:** Dynamic streak summary visible while positions are open; History merges lots/scaling from WS; profit-streak context in scaling rows; config warning when dynamic state resets.

---

## 2026-07-07 — Calendar Spread dynamic sizing and broker-flat fixes

### Fixed
- **Calendar Spread live:** Broker-flat reconciliation no longer treats missing Delta position rows as closed legs; requires both symbols present with size 0, confirmed twice before `broker_flat` close. Failed position fetches log exception type/message.
- **Calendar Spread live:** Removed tick-based `weak_running_pnl` scale-up; open spreads scale only when a closed trade bumps `currentLots` after the loss/profit streak threshold is met.
- **Calendar Spread live:** `is_weak_running_position` uses frozen target PnL band only (not bare `runningPnl <= 0`).

### Changed
- **Live dynamic quantity:** Scaling audit entries record pre-reset loss streak and threshold; Live tab shows target deploy size vs trade lots and last bump context; History scaling rows show streak-at-bump and triggering close id.
- **Logging:** `dynamic_qty advance`, `dynamic_qty scale decision`, and `broker_flat check` INFO lines for post-mortems.

---

## 2026-07-05 — MOVE Straddle product selection and anchor alignment

### Fixed
- **MOVE Straddle backtest:** MV product now resolves to the correct expiry — **next calendar day** when `startTime >= 17:30`, **same day** otherwise — then nearest ATM strike (fixes far-dated contracts with no mark candles at session open).
- **MOVE Straddle backtest:** Session anchor accepts the first mark candle in `[startTime, stopTime)` instead of requiring a bar within 15 minutes of anchor.

### Changed
- **Backtest diagnostics:** `sessionDiagnostics[]` entries include `targetExpiry`, `productExpiry`, and `expiryFallback`.

---

## 2026-07-05 — BTC MV Straddle Buy diagnostics and session fixes

### Fixed
- **MOVE Straddle backtest:** Pending buy-stops now cancel after 5 bars or at window end so later signals in the same session are not blocked (fixes artificially low trade counts).
- **MOVE Straddle backtest:** MV sessions accept first candle up to 15 minutes after anchor when exact 18:30 bar is missing (`no_anchor_bar` exclusions reduced).
- **Session window:** When `stopTime` is earlier on the clock than `startTime`, stop applies on the **next** IST calendar day (overnight window).

### Added
- **Backtest diagnostics:** `sessionDiagnostics[]` and `diagnosticSummary` in job result; per-day signal/pending/fill counts and events.
- **UI:** Session diagnostics table + expandable full JSON debug output on Move Straddle backtest tab.
- **Logging:** `cryptobridge.move_straddle.backtest` INFO lines per session day (product, bars, exclusions, signals).

---

### Changed
- **MOVE Straddle page:** Replaced 0DTE short strangle with **BTC MV Straddle Buy** — long MV mark straddle on 5m candles, user **startTime** / **stopTime** (defaults 18:30–22:30 IST), shooting-star below 5 EMA, buy-stop entry, 6R/20R partial exits with breakeven, 2 full-SL daily halt. Backtest API body is now `riskAmount`, `startTime`, `stopTime` (breaking change vs strangle fields).

### Removed
- **Daily Strangle backtest:** strike selection, moneyness, per-leg option SL, and 07:00/17:00 strangle session rules from `/move-straddle`.

---

### Fixed
- **Calendar Spread live config:** form no longer seeds from empty `{}` before the API responds (which reset saved settings to defaults). Sync waits for `config.userId`, respects in-progress edits, and re-applies after save.
- **Calendar Spread tabs:** Live/History/Backtest panels stay mounted (`hidden` toggle) so live settings panel state and loaded config survive tab switches.
- **Dark mode forms:** native `select`/`input` controls use `color-scheme: dark` so dropdown values stay visible on zinc fields.

---

## 2026-07-05 — CryptoBridge SVG logo restored

### Fixed
- **Branding:** workspace UI again shows `public/Cryptobridge.svg` via shared `CryptoBridgeLogo` — header, login/register, settings modal, system footer; dynamic-sizing guide page gets favicon + header logo. Replaces interim "CB" text monogram from the shell rebuild.

---

## 2026-07-04 — Header spot chips flicker fix

### Fixed
- **Live prices (header):** partial WebSocket ticks (`mark_price` / `ob_l1` / `ticker` on separate channels) no longer replace the full tick with explicit `null` bid/ask fields — `mergeLivePrices` patches only present values so BTC/ETH chips stay visible between updates.
- **Live prices (wire format):** backend `live_tick_dict` omits null quote fields; `/ws/live` always fans out the merged in-memory ticker. Header chips keep a stable shell with last-known price instead of unmounting.
- **Header spot blink:** removed tick-direction color flash (`useTickDirection` cycled green/red → invisible `dark:text-zinc-800` on zinc chips every ~600ms). Header prices now use `useHeldTickDirection` (green/red held until next opposite move); neutral fallback is readable `dark:text-zinc-100`, not zinc-800.

---

## 2026-07-04 — Live prices: WebSocket-only fan-out

### Fixed
- **`/ws/live` prices:** removed the 250ms in-memory cache mirror loop; browser price ticks now flow only from Delta market-data WebSocket events via `LivePriceBroadcaster` (initial snapshot on connect still seeds the latest cached tick per symbol).

---

## 2026-07-04 — Delta API signature + WebSocket resilience

### Fixed
- **Delta REST:** Signed requests stamp `timestamp`/`signature` in an httpx send-time hook (not at queue time) — fixes intermittent `expired_signature` on `/v2/positions/margined` when the connection pool is busy. One automatic retry on `expired_signature`; clock offset learned from error context.
- **Delta private WS:** Disabled library protocol pings (`ping_interval=None`); uses Delta JSON `enable_heartbeat` + client `ping`. Exponential reconnect backoff.
- **Delta market WS:** Same keepalive fix — resolves `keepalive ping timeout; no close frame received` disconnects.
- **Positions REST polling:** Skips redundant `/positions/margined` refresh when private WS is subscribed and last refresh was <30s; coalesces concurrent refreshes per account. Post-trade sync still forces refresh.

## 2026-07-04 — Light/dark theme switcher + backtest panels

### Added
- **Theme:** Header **Light/Dark** toggle (`ThemeSwitcher`); preference stored in `localStorage` (`cryptobridge.theme`). Default remains dark.

### Changed
- **Theming:** `workspaceClasses.js` tokens use `light` + `dark:` variants across shell, cards, fields, modals, tables, and charts.
- **Backtest tabs:** Calendar Spread and Move Straddle backtest panels (setup, results, equity curve, trade ledger) follow active theme — no fixed white cards in dark mode.
- **Strike Advisor:** Result cards, percentiles, and advanced sections theme-aware.

### Fixed
- **Dark theme:** Removed remaining white `bg-white` / `slate-50` panels on backtest, settings modal, footer, nav, and dynamic-sizing tooltip.
- **Charts (light theme):** SVG chart surfaces (dashboard equity wave, allocation donut, payoff, equity curve, P&L grid, strike-advisor range bands) use `useChartTheme()` and `chartSurface()` — no hardcoded `bg-zinc-950` containers in light mode.
- **Text (light theme):** Page titles, labels, tables, live engine panels, history, positions, strike advisor, and dialogs use `textHeading` / `textBody` / `textMuted` tokens instead of hardcoded `text-zinc-*` (fixes invisible white-on-white text).

## 2026-07-04 — Calendar live settings collapse + dark charts

### Fixed
- **Calendar Spread Live:** Engine configuration collapsed by default; **Settings** gear button (left of Start/Stop Engine) toggles the panel. Strike apply still auto-expands settings.
- **Charts:** Payoff, equity curve, P&L heatmap, and history run panels use dark `zinc-950` backgrounds instead of white cards.

## 2026-07-04 — Workspace UI rebuild (dark terminal)

### Changed
- **Frontend:** Replaced light `slate-50` shell with dark zinc workspace (white header, lime accent, nav strip, toast, system footer). One component per file; thin `*Page.jsx` orchestrators; shared `utils/workspace/*` and `components/ui/*` primitives.
- **Calendar Spread:** Live engine config is inline (`CalendarLiveControls`); settings modal removed. Strike Advisor apply navigates to Calendar Spread with moneyness pre-filled.
- **Active Positions:** Open | Past Orders | Payoff Simulator sub-tabs with dark tables.
- **Docs:** `FEATURES.md` §17 frontend tree; `FRONTEND_SMOKE.md` workspace nav checklist.

## 2026-07-04 — Backend file-only logging

### Changed
- **Backend logging:** default is rotating file under `logs/cryptobridge.log` only (no stdout). Tail with `tail -f logs/cryptobridge.log`. `LOG_TO_FILE=false` falls back to console-only.

---

## 2026-07-04 — Live settings save + summary layout

### Fixed
- **Calendar Spread live settings:** PATCH `/calendar-spread/live/config` now accepts dynamic sizing, `deployCatchUp`, and related fields (they were dropped by the API model, so saves appeared to succeed but did not persist).
- **Calendar Spread live summary:** summary grid uses a responsive 2–4 column layout so fields no longer overlap on wide screens.

---

## 2026-07-04 — Overlapping spread PnL attribution + Live set tabs

### Fixed
- **Calendar Spread live:** when two spread sets overlap on a shared broker symbol (e.g. same weekly buy leg), per-trade running PnL, entries, and exit rules no longer use blended broker `entry_price` or full-leg unrealized PnL. Each trade keeps deploy fill entries; marks drive running PnL and take-profit/stop decisions.

### Changed
- **Calendar Spread live:** REST/WebSocket payload adds `openPositionBundles[]` (per-set `position`, `legs`, `payoff`). With multiple open sets, Live tab shows one **spread-set tab** per deploy (sell+buy together), combined PnL banner, and full summary/chart/legs for the active set.
- **Calendar Spread history:** open-run running PnL from WebSocket maps by trade `id`, not only the newest `openPosition`.

---

## 2026-07-03 — Dynamic sizing live guide + summary indicator

### Added
- **Calendar Spread live:** pulsing dynamic-sizing icon on the run summary when enabled; hover tooltip links to `/docs/calendar-spread-dynamic-sizing.html` (standalone guide with loss/profit examples and back link to the app).

---

## 2026-07-03 — Calendar Spread live dynamic position sizing

### Added
- **Live dynamic quantity:** streak-based deploy size (`dynamicQuantityState` on `calendar_spread_config`); immediate mid-trade scale-up on weak running PnL or loss streak, scale-down on profit streak when open leg is healthy; append-only `dynamicQuantityScaling[]` audit on each trade with reason codes; Live settings modal + History scaling section.

---

## 2026-07-03 — Active Positions sync after broker close

### Fixed
- **Active Positions:** Delta private WebSocket now subscribes to `positions` and `orders` with `symbols: ["all"]` (required by Delta — without it no live updates arrive). Position snapshot/delete/zero-size messages are parsed correctly; REST refresh on WS reconnect and every 15s MTM cycle clears stale legs when you close positions on the broker UI.

---

## 2026-07-03 — Calendar Spread backtest input persistence

### Added
- **Backtest config persistence:** per-user backtest form inputs saved in MongoDB (`calendar_spread_backtest_config`); restored on page load; auto-saved after edits and when a backtest runs. API: `GET` / `PUT` `/calendar-spread/backtest/config`.

---

## 2026-07-03 — Calendar Spread IST timestamps and full-width backtest

### Changed
- **Calendar Spread backtest:** page uses full viewport width (no max-width cap).
- **Calendar Spread history/live:** entry and exit times always formatted in **IST**; naive API datetimes treated as UTC; API emits UTC ISO strings with `Z` suffix. Forward-test entry time uses the configured deploy slot.

---

### Changed
- **Calendar Spread backtest:** **Exit** column shows sell/buy exit premiums per leg — green when that leg closed in profit, red when in loss; exit reason shown below in muted text.

---

## 2026-07-03 — Calendar Spread backtest exit time column and wider layout

### Changed
- **Calendar Spread backtest:** trade ledger adds **Exit time** (IST) per row; page width increased to `120rem` for the wider table.

---

## 2026-07-03 — Calendar Spread dynamic quantity unit fixes

### Changed
- **Calendar Spread backtest dynamic quantity:** normalize sub-1 max/step values as BTC/ETH when quantity is in lots (e.g. max `0.3` → 300 lots); convert quantity fields when switching lots/BTC; trade ledger shows both lots and BTC; validation catches unit mix-ups.

---

## 2026-07-01 — Calendar Spread backtest dynamic quantity

### Added
- **Dynamic quantity (backtest only):** optional position sizing — after N consecutive losses increase quantity by I (capped at max); after M consecutive profits decrease by D (floored at initial quantity). Breakeven trades do not affect streak counters. Toggle + inputs in backtest setup; summary shows `Dynamic(x lots)`; trade ledger **Quantity** column when enabled.
- **Backtest UI:** page width matches Active Positions (`max-w-[96rem]`); summary expiry labels use human-readable names (Next day, Weekly, …).

---

## 2026-07-03 — Calendar payoff chart aspect ratio

### Fixed
- **Calendar payoff chart:** Preserve 680×300 aspect ratio instead of stretching to full container width.

---

## 2026-07-01 — Calendar live deploy catch-up preference

### Added
- **Calendar Spread live settings:** When today's entry time (IST) has already passed, choose **deploy immediately** or **wait for next entry time** (`deployCatchUp`). Start button shows the same choice; backend skips same-day catch-up when `next_slot` is selected.

---

## 2026-07-01 — Calendar History equity curve and P&L grid

### Added
- **Calendar Spread History tab:** Cumulative **equity curve** (same green/red style as backtest) from closed live runs plus provisional open P&L; **daily realised P&L heatmap** (GitHub-style grid with intensity legend, year overview / all history toggle, hover tooltip). Grid starts at the month of the first trade; month labels show once per month.

---

## 2026-07-01 — Calendar live overlapping spreads

### Changed
- **Calendar Spread live:** Deploys a new spread each calendar day even when prior spreads are still open (matches backtest). WebSocket/REST payload adds `openPositions` and `openPositionsSummary`; `openPosition` remains the newest run. Stop with exit closes **all** open spreads. Sell-expiry scheduler closes each trade by document id.

### Notes
- **Live order:** Overlapping spreads on the same symbols net at Delta; per-trade PnL uses stored contract counts on exit but may drift if legs are shared.

---

## 2026-07-01 — Calendar backtest exit time

### Added
- **Calendar Spread backtest:** Configurable **exit time (IST)** on sell-leg expiry day (default **17:00**). Backtest form, API (`exitTime` on `POST /calendar-spread/backtest`), prefetch window, and time-based square-off honor the setting.

---

## 2026-07-01 — Daily Strangle strike selection modes

### Fixed
- **Daily Strangle backtest:** Option candle prefetch window now matches the backtest lookup (`exit + 5m`); fixes zero trades when strikes/premiums existed. Resolves same-day symbols from listed Delta products when available; surfaces `exclusionReasons` in stats when days are skipped.

### Changed
- **Daily Strangle UI:** Backtest form shows only the strike inputs for the selected mode (moneyness → strike type; min/max premium → single threshold; premium range → range min/max).

### Added
- **Strike selection:** Backtest form and API support `strikeSelection` — `moneyness`, `min_premium`, `max_premium`, or `premium_range` — plus strike type, min/max premium, and range min/max inputs.

### Changed
- **Daily Strangle:** Premium-based modes scan the strike ladder at deploy and pick CE/PE premiums closest to the configured threshold or range midpoint.

---

## 2026-07-01 — Daily Short Strangle replaces MOVE Straddle backtest

### Changed
- **MOVE Straddle page (Daily Strangle):** Strategy pivot from packaged `MV-*` spike/EMA entry to **0DTE short strangle** — deploy **07:00 IST**, same-day expiry, sell call + put at user moneyness with min/max premium filter, per-leg stop-loss (default 100% on premium), square-off **17:00 IST**.
- **Backtest API:** `POST /move-straddle/backtest` body now uses `deployTime`, `moneyness`, `minPremium`, `maxPremium`, `quantity`, `quantityUnit`, `stopLossMode`, `stopLossValue` (replaces `anchorTime`, `maxRisk`, `upmovePct`, `noTradeAfter`, `retryEnabled`, `debug`).
- **Backtest summary:** Calendar-style stats plus **win both legs**, **win 1 leg**, **lose both legs** (count and %).

### Removed
- **MOVE Straddle:** Spike/setup diagnostics, `MV-*` product prefetch, and verbose `diagnostics[]` / `diagnosticSummary` in backtest results.

---

## 2026-07-01 — MOVE Straddle per-day prefetch + session reset

### Fixed
- **MOVE Straddle backtest:** Prefetch one `MARK:MV-*` window per session day (from anchor), merging bars by timestamp — fixes `prefetchBarCount > 0` but `moveBarCount = 0` on earlier days. Each day resets at anchor C1 (`no_anchor_bar` when the anchor 5m candle is missing); spike `referenceOpen` matches `c1Open`.

### Changed
- **MOVE Straddle diagnostics:** `sessionWindowBarCount`, `prefetchTimeMin`/`Max`, `anchorBarTime`, `c1Open`; UI **Window bars** column.

---

## 2026-07-01 — MOVE Straddle mark-price candle prefetch fix

### Fixed
- **MOVE Straddle backtest:** Prefetch now requests Delta mark OHLC (`MARK:MV-*`) instead of raw product symbols, fixing `no_move_candles` when products resolve but trade candles are empty. Diagnostics include `candleFetchSymbol` and `prefetchBarCount`.

---

## 2026-07-01 — MOVE Straddle backtest diagnostic logging

### Added
- **MOVE Straddle backtest:** Per-session `diagnostics[]` and `diagnosticSummary` in job result when `debug` is true (default); structured spike/setup filter detail per calendar day.
- **MOVE Straddle UI:** Collapsible session diagnostics table + download JSON; verbose diagnostics checkbox on backtest form.
- **MOVE Straddle logs:** `cryptobridge.move_straddle.backtest` INFO lines per session (product selection, spike gate, setup scan).

### Changed
- **MOVE Straddle API:** `POST /move-straddle/backtest` accepts `debug` (default `true`); exclusion reasons are explicit (`no_spike`, `no_move_product`, `no_setup`, …) instead of opaque `no_trade` where possible.

---

## 2026-07-01 — MOVE Straddle configurable start time + persisted form

### Added
- **MOVE Straddle backtest:** `anchorTime` (IST session start, default `20:15`); backtest form settings persist in browser `localStorage`.

### Changed
- Default anchor time **20:00 → 20:15**.

---

## 2026-07-01 — MOVE Straddle upmove spike criteria (corrected)

### Changed
- **MOVE Straddle spike gate:** Anchor candle C1 open is the reference (e.g. 500). From C2 onward, lows must not break below C1 open until a candle closes with high ≥ C1.open × (1 + upmovePct/100) (e.g. 580 on C5). Entry filters apply only after that spike candle closes.

---

## 2026-07-01 — MOVE Straddle upmove spike criteria

### Changed
- **MOVE Straddle spike gate:** A closed candle qualifies when its high reaches `upmovePct` % above its own open and its low does not break below that open (replaces close vs 8 PM baseline).

---

## 2026-07-01 — MOVE Straddle backtest completion fix

### Fixed
- **MOVE Straddle backtest:** Results no longer hang on "processing" — frontend polls `GET /move-straddle/live` while a job runs; candle prefetch is concurrent and scoped per contract; simulation runs off the event loop so WebSocket updates still deliver.

---

## 2026-07-01 — MOVE Straddle spike % input

### Added
- **MOVE Straddle backtest:** `upmovePct` — user-configurable minimum premium spike % from 8 PM baseline (default 15).

### Changed
- **MOVE Straddle UI:** max risk displays without a leading `+` (uses money formatter, not PnL formatter).

---

## 2026-07-01 — Daily MOVE Straddle backtest

### Added
- **MOVE Straddle page:** backtest for Delta India Daily MOVE (`MV-*`) — 5m EMA setup after 15% spike, max-risk sizing, T1/T2/17:00 management, optional retry after SL; calendar-style summary, equity curve, and trade ledger. Live tab disabled (501 on start).

---

### Added
- **Calendar Spread live:** `stopLossCapMode` in live settings — **`capped`** (default, `min(configured stop, take profit)`) or **`configured_only`**. Saving settings that change take-profit, stop-loss, or stop cap **re-freezes** `targetPnl`/`stopPnl` on the open run from actual entry fills.

### Changed
- **Calendar Spread backtest:** stop cap control no longer labeled backtest-only; same options apply to live and backtest.

---

## 2026-07-01 — Calendar Spread backtest stop-loss cap option

### Added
- **Calendar Spread backtest:** `stopLossCapMode` — **`capped`** (default, `min(configured stop, take profit)`) or **`configured_only`** (use stop % / points without take-profit cap).

### Fixed
- **Calendar Spread backtest:** `stopLossCapMode` was dropped by the API request model, so configured-only always fell back to capped; field is now accepted on `POST /calendar-spread/backtest`.
- **Calendar Spread backtest:** trade table pagination reset to page 1 on Next/Prev because live WebSocket updates re-applied the same result; page now resets only on a new backtest job or page-size change.
- **Calendar Spread backtest:** equity curve shows a zero PnL baseline with green line/shade above and red below.

---

## 2026-07-01 — Strike Advisor price range focus + model fixes

### Changed
- **Strike Advisor:** primary forecast output is **80% probable 17:00 IST spot range** (`exit17PriceRange` P10–P90, median P50 headline); horizon `rangeBand` unchanged; strike suggestion demoted to nearest-to-median for Calendar apply only.
- **Strike Advisor:** models train on **log-return targets** (`FEATURE_VERSION` 2); deeper history via `STRIKE_FORECAST_HISTORY_STEPS` (default 4 × 180d = 720d); sample cap raised to 150k; UI shows MAPE, recent 14d MAE, and low-confidence warning when holdout error &gt; 8% of spot.

### Fixed
- **Strike Advisor:** suggested strike no longer driven by MC vote on a spot-anchored ladder (fixes far-OTM strike vs high predicted spot mismatch).

---

## 2026-07-01 — Calendar Spread Live summary typography

### Changed
- **Calendar Spread Live:** Summary values and per-leg trade table use terminal-style monospace; wide-screen Summary grid uses content-sized columns with spacer gutters between field pairs (tight label–value gap, wider gap between fields). Trade details columns except Instrument are center-aligned.

---

## 2026-07-01 — Strike Advisor training performance and responsiveness

### Fixed
- **Strike Advisor:** training sample builder uses bisect lookups (was O(n²) per sample) and a coarser origin step so manual **Train model** finishes in reasonable time without freezing the app.
- **Strike Advisor:** `GET /model-status` reads Mongo metadata only (no pickle decode on poll); pickle encode/decode and sklearn predict/MC paths run in worker threads.
- **Strike Advisor:** `model-status` includes active `trainJob` / `forecastJob` for polling fallback when WebSocket delivery is missed; page polls every 3s while a job is pending.

### Changed
- **Strike Advisor:** training GBM `n_estimators` reduced from 120 → 60 for faster retrains with similar holdout quality.

---

## 2026-07-01 — Strike Advisor train without blocking server

### Fixed
- **Strike Advisor:** model training (sklearn fit) now runs in a worker thread so the FastAPI event loop stays responsive. **Train model** submits an async job and pushes `trainJob` over WebSocket when complete (same pattern as forecast).

---

## 2026-07-01 — Strike Advisor async forecast (no HTTP timeout)

### Changed
- **Strike Advisor:** `POST /api/strike-advisor/forecast` now returns immediately with `{ status: "processing" }` (same pattern as calendar backtest). Training + inference run in a background job; results push over WebSocket `type: strike_forecast` with `forecastJob` when complete.

---

## 2026-07-01 — Strike Advisor (ML + LLM)

### Added
- **Strike Advisor:** new nav page trains Gradient Boosting models on Delta historical 5m spot candles, forecasts a configurable price band over user horizon hours, and ranks strikes by probability of being closest to spot at 17:00 IST on the sell-leg expiry day. Optional OpenAI narrative when `OPENAI_API_KEY` is set. **Apply to Calendar Spread** patches live `sellMoneyness`. APIs: `POST /api/strike-advisor/forecast`, `GET /api/strike-advisor/model-status`, `POST /api/strike-advisor/retrain`. Models stored in MongoDB `strike_forecast_models`.

---

## 2026-07-01 — Calendar fills show in Active Positions

### Fixed
- **Active Positions / dashboard:** after calendar spread live orders fill, the backend now refreshes the broker position cache and immediately rebroadcasts `type: positions` (with follow-up retries while REST catches up). Previously only trade close triggered a refresh, so new legs stayed invisible until a manual reload.

---

## 2026-07-01 — Active Positions live PnL refresh

### Fixed
- **Running PnL:** open position symbols (options and perps) are subscribed to the public mark stream when a live client connects; each tick rebroadcasts refreshed positions and the frontend recomputes UPNL from live marks. A 15s MTM loop covers sparse option ticks.

---

## 2026-07-01 — Calendar ATM strike ranks by distance to spot

### Fixed
- **ATM strike snap:** bilateral candidates are ranked by distance to **live spot** (not the ladder-snapped anchor), so spot 57,949 picks **58,000** over **59,000** when both are tradeable. Strike grid step uses near-the-money listings and unions actual strikes in the spot band.

---

## 2026-07-01 — Calendar strike snap stays near ATM

### Fixed
- **Strike selection:** bilateral snap no longer scans 16 grid steps or prefers far strikes with higher modeled peak profit. The engine keeps strikes within a small snap window around the moneyness target (closest first, then CE/PE by sell-expiry peak). Live strike grids rebuild when spot drifts outside the cached band.

---

## 2026-07-01 — Calendar max-profit CE/PE, bilateral strike search, USD 2dp

### Changed
- **Calendar strike selection:** when the moneyness-resolved strike is not on both expiries, the engine searches **outward on both sides** of the grid anchor for tradeable strikes, scores each valid CE and PE calendar by **max profit at sell-leg expiry**, and picks the global best (tie-break: closer to resolved strike, then lower debit). Applies to backtest, live deploy, flat preview, and ticker fallback.
- **USD money display:** premiums, PnL, debit, margins, and commissions across Calendar Spread and Active Positions always render with **two decimal places** (`formatUsdMoney` / `formatPnl` / `formatPremium`); browser tab running P/L uses the same rule.

---

## 2026-07-01 — Calendar spread strike snap + CE/PE debit pick

### Changed
- **Strike resolution:** when the moneyness-resolved strike is not listed on both sell and buy expiries, the engine snaps to the closest grid strike with premiums on both legs, then chooses **CE vs PE** by lowest net debit at that strike (live deploy, preview, and backtest). *(Superseded by max-profit bilateral search above.)*

---

## 2026-07-01 — Active Positions payoff graph fix

### Fixed
- **Active Positions payoff:** selecting two calendar-spread legs now builds the correct near-expiry tent (short leg intrinsic + far leg Black–Scholes at residual TTE), matching the Calendar Spread tab and industry calendar-spread calculators.
- **Option PnL scale:** generic payoff curves multiply premium change by `signedBaseUnits` (same scale as live UPNL), fixing ~1000× inflated Y-axis for BTC options.
- **Symbol matching:** calendar WS payoff is used when both strategy leg symbols are selected (normalized case); manual two-leg calendars without a live engine still get the calendar model via frontend detection.

---

## 2026-07-01 — CryptoBridge logo, favicon, and tab running P/L

### Changed
- **Branding:** app logo and favicon now use `public/Cryptobridge.svg` (header, footer, login, browser tab icon).
- **Browser tab title:** shows `CryptoBridge :: +200.77` (signed running unrealized P/L) when there are open positions or a live calendar-spread run; otherwise `CryptoBridge`.

---

## 2026-07-01 — Calendar Spread frozen auto-exit + scoped leg close

### Fixed
- **Auto-exit thresholds frozen at deploy:** max profit, max loss, target profit, and stop-loss PnL are computed once at deployment (re-frozen after live-order broker entry reconcile) and persisted on `calendar_spread_trades`. Running PnL is compared against these fixed bounds on each price tick — target/stop lines no longer drift with live IV/spot.
- **Granular exit reasons:** live auto-exit now records `stop_loss` / `profit_target` instead of a generic `rule`.
- **Scoped strategy close:** `_close_live_orders` closes only this run's sell/buy symbols at `sellContracts`/`buyContracts` (capped by broker size on those symbols); uses the trade's `accountId`; other open positions are not touched.

### Changed
- **Backtest:** `simulate_spread_exit` uses the same `compute_deployment_exit_thresholds` helper as live for aligned stop/target math.

## 2026-06-30 — Calendar spread UI clears after 17:00 exit

### Fixed
- **Calendar Live + Active Positions after exit:** when both calendar legs are flat at Delta (e.g. after the 17:00 sell-expiry close fills), the app now marks the run closed in MongoDB, refreshes the broker positions cache, and pushes an updated WebSocket payload with no open position. Previously the private-stream handler ignored flat legs and stale REST/WS state could leave closed options visible on Active Positions and the Calendar Live tab.

---

### Changed
- **Live tab heading** is now **Calendar spread** (removed "forward-test" suffix).

---

### Fixed
- **Breakeven now computed reliably:** calendar spread breakevens use bisection on the continuous payoff function (near-leg intrinsic + far-leg Black–Scholes at residual TTE) instead of depending on a coarse sampled curve. The chart x-range is widened to include both breakeven wings.
- **Payoff chart:** strike vertical, breakeven markers with price labels, max profit/loss legend, and preview summary (strike/breakeven/max P&L) when flat.

---

## 2026-06-30 — Calendar Spread entry sync + CoinDCX removed

### Changed
- **Calendar Spread live entry matches broker:** for live-order runs, sell/buy entry premiums are taken from Delta position `entry_price` (the same value shown on the exchange) after orders fill, with order `average_fill_price` as fallback. Open live runs re-reconcile entry from broker positions on each status refresh so the Live tab stays in sync.
- **CoinDCX integration removed:** the app is Delta-only — accounts, arbitrage funding monitor, spread execution, opportunities, and Active Positions no longer connect to or display CoinDCX. Arbitrage funding shows Delta perp rates only.

### Removed
- CoinDCX REST client, env vars (`COINDCX_*`), account type, UI selectors, and all dual-venue spread/opportunity execution paths.

---

## 2026-06-30 — Active Positions option PnL matches the exchange

### Fixed
- **Option running PnL now matches Delta's UPNL:** Delta's `/v2/positions/margined` reports `unrealized_pnl` for option legs with the premium cashflow folded in, so the Active Positions cards diverged from the exchange UI. Running PnL for Delta **option** legs (`C-*` / `P-*`) is now recomputed mark-to-market as `side × (mark − entry) × contract_value × contracts` (BTC `0.001`, ETH `0.01`, or the position's own `contract_value`), matching the UPNL column shown on Delta. Perp positions still use the broker-reported `unrealized_pnl`.

---

## 2026-06-30 — Calendar Spread stop confirmation + reliable fills

### Added
- **Stop confirmation:** stopping the Calendar Spread live engine while a position is open now opens a confirmation dialog with an **"Exit all running positions under this strategy"** checkbox. Checked → both legs close at market; unchecked → the engine stops deploying but the open position keeps running under its stop/target/expiry rules. `/calendar-spread/live/stop` now accepts `{ exitPositions: bool }` (default true).

### Fixed
- **Entry/exit price now reflects the real fill:** live-order entry and exit prices are resolved from the broker's actual `average_fill_price`, re-fetching the order once (`fetch_order`) when the synchronous place-order response hasn't reported the fill yet. Previously the displayed entry could fall back to the execution-time quote and not match the actual fill.
- **Entry time is the actual order time:** for live orders, a run's entry time (`deployedAt`) is now taken from the broker order's `created_at` rather than when the trade document was built.

---

## 2026-06-30 — Calendar Spread History tab + actual fills

### Added
- **History tab** on the Calendar Spread page lists **all live runs** (forward test & live order), newest first, including the currently-running one, as collapsible panels. Each panel shows entry time, **exit time, exit reason**, actual entry/exit premiums, net debit, max profit/loss, target/stop, leg symbols, order IDs, and running/realized PnL. New endpoint `GET /api/calendar-spread/history`. The list is event-driven off the live WebSocket (reloads on open/close; running PnL stays live) — no polling.

### Changed
- **Live orders record actual fills:** live-order entries and exits now store the broker's **average fill price** (added `OrderSummary.average_fill_price`) instead of the execution-time mark. Entry premiums, net debit, running PnL and realized PnL all reflect real fills; the originally quoted marks are retained as `quotedSellEntry`/`quotedBuyEntry`/`quotedDebit`. The Live tab therefore shows actual entry and PnL.

---

## 2026-06-30 — Paginate Calendar Spread backtest results

### Added
- **Paginated backtest table:** the Calendar Spread backtest results table now paginates with a user-adjustable rows-per-page selector (10/25/50/100, default 25), Prev/Next controls, and an "X–Y of N" counter. Page resets to 1 on a new run or page-size change.

---

## 2026-06-30 — Remove Calendar Spread backtest-only banner

### Removed
- **"Backtest only — no live orders" banner** removed from the Calendar Spread Backtest tab.

---

## 2026-06-30 — Calendar Spread quantity follows underlying

### Changed
- **Quantity unit tracks the underlying:** in the Calendar Spread backtest form, switching the underlying (BTC ↔ ETH) now switches the coin-denominated quantity unit to match (lots are left unchanged), and the unit dropdown only offers `lots` + the selected underlying — so the quantity can no longer be denominated in the wrong coin.

---

## 2026-06-30 — Calendar Spread live entries at market

### Changed
- **Calendar Spread live orders always enter at market:** both legs are now placed as `market_order` (no `limit_price`) so they fill immediately, removing the risk of a resting limit order leaving one leg unfilled. Exits already used market reduce-only orders.

---

## 2026-06-30 — Coin icons

### Added
- **Coin icons (BTC/ETH/SOL):** new `CoinIcon` component renders the coin glyph from `public/{btc,eth,sol}.svg` with a lettered-badge fallback for coins without an icon. Used in the header live BTC spot pill, the Near-ATH scanner cards, the Calendar Spread underlying selector, and the Directional Options "BTC price" stat.

---

## 2026-06-30 — Calendar Spread weekly expiry roll

### Changed
- **Weekly expiry skips near-term Fridays:** the `weekly` expiry mode now rolls to the *following* Friday when the nearest weekly is within 3 days of the deploy date (e.g. deploying Tue → the Friday 3 days out is skipped to the next week's Friday), so the long leg always has meaningful time to expiry. Affects calendar spread `sellExpiry`/`buyExpiry = weekly`.

---

## 2026-06-30 — Calendar Spread payoff chart shape & fill

### Fixed
- **Payoff chart now matches the classic calendar tent:** the chart fills the profit region above breakeven green and the loss wings below breakeven red (split at the dashed zero line) with `PROFIT` / `LOSS` labels, instead of a single green fill under the whole curve.
- **Realistic profit peak:** the far leg is now repriced at its *own* implied volatility (backed out from the far-leg premium at full time-to-expiry) for both the flat preview and open positions, rather than borrowing the short (near) leg's vol. This restores the expected profit hump around the strike instead of a distorted/all-loss curve.

---

## 2026-06-30 — Calendar Spread Live fixes

### Fixed
- **Live prices stream over WebSocket (no polling):** the Live engine now pushes status updates off the Delta market-data price WebSocket. On connect a client is registered (`attach_live_client`), its calendar option symbols (CE & PE candidates, or open-position legs) are subscribed once, and updates are pushed per-user as ticks arrive (debounced ~1s). The per-user broadcaster prevents cross-user leakage; the frontend 8s REST poll was removed.
- **Payoff chart preview when flat:** with no open position the engine subscribes both CE and PE legs for the configured strike/expiries and shows a loader until live ticks arrive; once marks stream it picks the lower-debit side and renders the live payoff (priced only from live ticks, no theoretical fallback).
- **Open-position Running PnL consistency:** the summary Running PnL is recomputed from current WebSocket marks (`((sellEntry − sellMark) + (buyMark − buyEntry)) × qty`) instead of the stale stored value, so it matches the per-leg running PnL.
- **Time-based exits unchanged:** stop-loss / take-profit are evaluated on price ticks; the 17:00 IST sell-leg expiry exit runs on a lightweight clock-only scheduler (no Delta polling).
- **Countdown format:** deploy/expiry countdowns now render as `HH:MM:SS`.
- **Settings no longer reset while editing:** the live settings modal seeds its form only when opened, so incoming live WebSocket updates (which refresh the config reference every tick) no longer wipe in-progress edits.

## 2026-06-30 — Calendar Spread Live tab

### Added
- **Calendar Spread Live tab:** Backtest | Live pill tabs on `CalendarSpreadPage`. Live tab supports **Forward test** (simulated) and **Live order** (real Delta orders via Arbitrage account settings). Settings modal: underlying, entry time (IST), lots, moneyness strike, sell/buy expiry, take-profit and stop-loss (points/%). Start/Stop controls, summary panel, SVG payoff chart (live spot, target/stop lines, breakevens), per-leg details table, deploy and expiry countdowns. REST `GET/PATCH/POST /api/calendar-spread/live*` + WebSocket `type: calendar_spread` (`topic: calendar`).
- **Backend live engine:** `CalendarSpreadLiveMixin` — Mongo collections `calendar_spread_config` / `calendar_spread_trades`, deploy scheduler, MTM/exit loop, payoff helpers (`calendar_payoff_curve`, breakevens, extremes).

## 2026-06-30 — Exchange-scoped candle cache for backtests

### Added
- **Persistent candle cache (`CandleCacheService`):** historical Delta candles fetched for backtesting are now cached in MongoDB **scoped by exchange** (e.g. `delta`), not by account — so multiple Delta accounts share one cached history. New collections `candle_cache` (one doc per `(exchange, symbol, resolution, time)`) and `candle_cache_coverage` (fetched time-range tracking). Backtests read cached bars and only hit the Delta API for uncovered ranges; the still-forming latest candle is not marked covered so it refreshes. Wired into Calendar Spread, Directional Options, and Move Fade backtests. Verified: a repeated Calendar Spread run dropped from 191 Delta API calls to 1 with identical results.

## 2026-06-30 — Calendar Spread: real strike grid + per-unit premiums

### Fixed
- **ATM strike selection:** ATM was rounded to a fixed step (1000 for BTC), snapping spot like 60,601 to 61,000 — hundreds of dollars off — and surfacing far-OTM premiums (e.g. a "129" sell premium). ATM and moneyness offsets now snap to Delta's **real listed strike grid** (derived from recently-expired option contracts; e.g. 200 for BTC, 10 for ETH), so entry premiums reflect the true at-the-money option.
- **Illiquid far-leg strikes:** each leg now snaps to the nearest strike that has data on **both** expiries (outward search along the grid), removing spurious "excluded" days when an odd strike was untraded on the far expiry.

### Added
- **Configurable take-profit:** Calendar Spread now exposes a take-profit input with **Points** ($) or **Percentage** (of max profit) modes, mirroring stop-loss (`takeProfitValue`/`takeProfitMode`). Defaults to 70% (previous hard-coded behavior); `0` disables the profit-target exit.

### Changed
- **Premiums shown per 1 BTC/ETH:** entry/exit sell- and buy-leg premiums are always per 1 unit of the underlying; max profit, max loss and total PnL are scaled by the selected quantity. UI labels and the table headers now state this explicitly.
- **Trades table:** added **Sell expiry** and **Buy expiry** columns.

## 2026-06-30 — Daily Calendar Spread backtest

### Added
- **Calendar Spread page (`CalendarSpreadPage`, nav "Calendar Spread"):** backtest-only daily calendar spread on Delta BTC/ETH options. Each day at deploy time (IST), sells the near expiry and buys the same strike at a farther expiry. Both CE and PE are evaluated; the lower-debit spread is used. Optional IV filter (±4 around target IV via inverse Black-Scholes). Exit both legs on stop-loss, 70% of max profit, or 17:00 IST on sell-leg expiry day. Summary stats (days traded/excluded, streaks, drawdown) + details table with per-leg entry/exit premiums.
- **Backend:** `CalendarSpreadService`, `utils/calendar_spread_helpers.py`, `utils/calendar_spread_backtest.py`, `POST /api/calendar-spread/backtest`. Option legs priced from Delta historical option candles (5m/15m).

---

## 2026-06-28 — Move Fade Writer (backtest)

### Added
- **Move Fade** top-level page: Delta-only strategy backtest with **Move Study** (how often BTC hits separate up/down % thresholds from the 6:30 PM IST anchor) and **Strike Ladder** (ITM10…ATM…OTM10 sweep using real historical option candles).
- **Rules modeled:** lock-in on first threshold touch, entry at next Delta hourly close (:30), SL 130% / TP 80% decay / one re-entry, 9 AM IST expiry rule.
- **Backend:** `MoveFadeService` + `utils/move_fade_backtest.py` + `POST /api/move-fade/move-study` + `POST /api/move-fade/backtest`.

---

## 2026-06-28 — Analysis: Highest Funding tab (normalized to 8h)

### Added
- **Analysis page:** new **Highest Funding** tab between Top Gainers and Near ATH. Lists Delta perpetuals ranked by funding rate normalized to a per-8h basis (highest first), with each card showing the per-8h funding %, native rate, funding interval badge, price, and a live next-funding countdown.
- **Backend:** `MarketInsightsService.highest_funding(limit)` + `GET /api/market/highest-funding?limit=30`. Normalizes per-interval funding to per-8h (`perInterval × 8 / intervalHours`) using shared arbitrage helpers; skips contracts with no funding rate.

---

## 2026-06-28 — Unified positions and orders (all accounts)

### Changed
- **Active Positions tab:** now shows all open positions and open orders across every connected Delta and CoinDCX account — including trades placed directly on the broker, not only app-created spread trades. Positions are tagged **App** or **Broker**; spread trades still show the rich dual-leg card with Close action.
- **Live sync:** Delta uses private WebSocket (`positions` + `orders` channels on all connected Delta accounts); CoinDCX refreshes via REST poll (~5s). Consolidated `type: positions` payload streams over `/ws/live` (topic `positions`).
- **Past Orders tab:** order history grouped by broker (Delta `/v2/orders/history`, CoinDCX futures orders list).

### Added
- **Backend:** `PositionsService` + `GET /api/positions/open` + `GET /api/positions/history?broker=all|delta|coindcx`; `utils/positions_helpers.py` for reconciliation/mapping; Delta REST `fetch_orders_history` / `fetch_fills`; CoinDCX `fetch_futures_orders`; `AccountService.list_raw_accounts`.

---

## 2026-06-28 — Funding over WebSocket + Analysis tab (Top Gainers)

### Changed
- **Arbitrage funding is now event-driven over WebSocket:** Delta funding rates stream from the public `funding_rate` WS channel instead of REST polling. `DeltaMarketDataService` subscribes `funding_rate` for every perpetual, maintains a `latest_funding` cache, and notifies listeners on each tick. `ArbitrageService` rebuilds and broadcasts the `arbitrage_funding` snapshot from cache whenever Delta funding changes (bursts coalesced within ~1s). CoinDCX has no public funding WS, so its funding stays on an isolated REST refresh (`COINDCX_REFRESH_SECONDS`, 15s) that also triggers a rebroadcast. `/api/arbitrage/meta` now reports `deltaFundingSource: "websocket"` and `coindcxRefreshSeconds` instead of `pollIntervalSeconds`.

### Added
- **Analysis page (renamed from "Near ATH"):** the nav item is now **Analysis** with two tabs — **Top Gainers** (new, default) and **Near ATH** (the existing scanner, unchanged).
- **Top Gainers tab:** perpetuals ranked by 24h % gain, each card showing price, current funding rate, and the **funding-rate change over the last ~8h** with a trend arrow. A pill flags coins whose funding is **favorable** (positive, or negative-but-rising). Backend: `MarketInsightsService.top_movers(limit, funding_window_hours)` + route `GET /api/market/movers`; funding history comes from Delta `FUNDING:<symbol>` candles (cached, 15m TTL), fetched only for the top-N gainers.

---

## 2026-06-28 — Near All-Time High scanner

### Added
- **Near ATH page (`NearAthPage`, nav "Near ATH"):** scans all Delta perpetual futures and shows, as coin cards, those trading **within N% of their all-time high** (threshold selector 5/10/15/25%, default 5%). Each card shows current price, all-time-high price, % below ATH with a proximity bar, and the ATH date.
- **Backend:** `MarketInsightsService.near_ath(thresholdPct)` + route `GET /api/market/near-ath`. ATH is derived from **weekly** Delta candles (one request per symbol), cached per symbol (6h TTL); current price is read fresh from the perp ticker feed and a live price above the cached high is treated as a new high. `utils/near_ath_helpers.py` holds the pure math (`drop_from_ath_pct`, `is_within_threshold`, `clamp_threshold_pct`) with tests. Note: "all-time high" is bounded by the candle history Delta serves for each contract.

---

## 2026-06-27 — Active Positions: per-exchange running PnL & cashflow

### Added
- **Per-exchange breakdown on each position card:** every Active Positions card now shows **running PnL** and **cashflow (funding)** for **Delta** and **CoinDCX** separately, plus a **Total** running PnL and total cashflow row. Page header gained **Open running PnL** and **Open cashflow** summaries.

### Fixed
- **CoinDCX running PnL always showed 0:** the CoinDCX positions endpoint returns no `pnl` field, so it's now computed from `active_pos × (mark_price − avg_price)`. Per-exchange unrealized PnL (`deltaUnrealizedPnlUsd`, `coindcxUnrealizedPnlUsd`) is persisted alongside the total.
- **Funding/cashflow was never populated:** Delta funding now reads the position's `realized_funding`; CoinDCX funding is summed from funding-stage transactions (`derivatives/futures/positions/transactions`, `stage=funding`). Stored as `deltaFundingUsd` / `coindcxFundingUsd` and totalled into `fundingCollectedUsd`.

---

## 2026-06-27 — Fix CoinDCX futures order rejected (HTTP 400)

### Fixed
- **CoinDCX order create returned 400 (empty body):** `create_futures_order` sent a flat payload, but CoinDCX's `derivatives/futures/orders/create` requires the order fields **nested under an `order` object** with a mandatory `notification` field. Orders are now built as `{"timestamp", "order": {…, "notification": "no_notification"}}`, `time_in_force`/`price` are omitted for market orders (per docs), and the list response (`[{…}]`) is unwrapped to the first order. The CoinDCX order id is now persisted on the spread trade (`coindcxOrderId`).

---

## 2026-06-27 — Fix leverage read as 1x (spread sizing failures)

### Fixed
- **"Could not size a valid spread trade" from max leverage = 1:** both venues were collapsing to 1x, so small margins couldn't afford one contract.
  - **Delta:** `max_leverage_for_product` ignored the product's `default_leverage` (it was only read from a node that wasn't passed) and treated `initial_margin` as a fraction. `default_leverage` is now captured on `ProductSummary` and used directly (e.g. LABUSD → 20x), and the `initial_margin` fallback is correctly read as a **percentage** (`100 / initial_margin`).
  - **CoinDCX:** `max_leverage_for_side` returned 1 when `max_leverage_long/short` were `null`. It now falls back to `max_leverage` and, finally, the highest tier in `dynamic_position_leverage_details` (e.g. `{"2":…,"30":…}` → 30x).

---

## 2026-06-27 — CoinDCX futures wallet: correct GET endpoints

### Fixed
- **CoinDCX balance 502 ("futures wallet balance unavailable"):** margin was fetched only via `cross_margin_details` using POST, but CoinDCX's API docs show both wallet endpoints are **signed GETs with a JSON body**. Balance now comes from `GET /derivatives/futures/wallets` (primary — always returns the USDT futures wallet even with no open positions) and is refined by `GET /derivatives/futures/positions/cross_margin_details` when available (`available_balance_cross`, `total_account_equity`). Spot USDT is still excluded.

### Changed
- **CoinDCX balance/margin source:** `fetch_margin_overview` uses the two futures-wallet GET endpoints above (not spot `users/balances`). Applies to account display, spread-execution sizing, and opportunity quotes.

---

## 2026-06-27 — Spread execution logging / observability

### Added
- **Step-by-step spread execution logs:** the manual **Arbitrage** button and auto execution now log every step — request received, account resolution, Delta/CoinDCX available balances and computed margin, funding row, sized plan (sides/price/qty/leverage), Delta leverage change + order placement, CoinDCX order placement, and the persisted trade — under the `[spread]` prefix. Failures log full tracebacks; rejections log status + reason.
- **Sizing rejection reason:** when "Could not size a valid spread trade for X" is returned, the manual path now logs the exact sizing inputs (best bid/ask, margin, target vs. effective leverage, Delta contract value, CoinDCX min lot / increment) and the specific guard that failed (e.g. affordable qty below the CoinDCX minimum lot, or below one Delta contract).
- **REST call tracing:** Delta (`[delta]`) and CoinDCX (`[coindcx]`) signed POSTs log the request body and response status (and error body on failure). API keys and HMAC signatures are never logged.

### Fixed
- **`LOG_LEVEL` was not applied:** logging is now configured at startup from `LOG_LEVEL` (default `INFO`), so application logs (including the above) actually surface. Set `LOG_LEVEL=DEBUG` for more detail.

---

## 2026-06-27 — CoinDCX wallet balance now shown

### Fixed
- **CoinDCX margin showed 0.00 / unavailable:** account enrichment previously fetched balances for Delta accounts only, so connected CoinDCX accounts never displayed a balance. CoinDCX accounts are now enriched via `CoinDcxRestClient.fetch_margin_overview`, which combines the USDT **futures wallet** (`derivatives/futures/positions/cross_margin_details`) with the **spot USDT** balance (`users/balances`) so funds in either wallet are reflected in available margin / balance / equity (currency `USDT`).

### Changed
- **Spread execution + opportunity sizing:** CoinDCX available margin for auto/manual arbitrage and opportunity quotes now uses `fetch_available_margin` (same combined futures + spot USDT source as account display), not spot USDT alone.

---

## 2026-06-27 — Account Settings modal polish

### Changed
- **Account Settings → Arbitrage:** removed the redundant "Delta account" / "CoinDCX account" label text — the exchange is now identified by its brand logo alone; selector placeholders/warnings are generic ("Select account").
- **Account Settings modal:** now has a fixed size across all sidebar sections (content scrolls internally) so it no longer resizes when switching between Profile/Trading Account/Arbitrage/Spread Execution/API.

---

## 2026-06-27 — Directional options: 2-week expiry + real historical-data backtest

### Changed
- **Directional Options (live):** the strategy now always sells the **~2-weeks-out** expiry — the listed BTC expiry closest to `today + 14 days` (`select_expiry_near_days`) — instead of the front-monthly expiry.
- **Directional Options backtest:** premiums now come from **Delta's actual historical option candles** per contract (`/v2/history/candles`) instead of a Black-Scholes model. The engine plans signal-driven legs, derives each leg's option symbol (e.g. `C-BTC-95000-310325`), fetches its real OHLC, and prices entry/exit (stop-loss on candle-high breach; expiry settled to intrinsic). Legs with no available contract history are skipped rather than modelled.

### Removed
- Backtest inputs **Implied volatility %**, **Risk-free rate %**, and **Expiry mode / Days to expiry** (no longer used); added **Target expiry (days)** (default 14). Response adds `legsPlanned`, `legsPriced`, `legsSkippedNoData`, `premiumSource`.

---

## 2026-06-27 — Arbitrage account selection in Account Settings

### Added
- **Account Settings → Arbitrage:** new sidebar section with a per-exchange account selector (Delta + CoinDCX) used for arbitrage trading. Auto-selects (and persists) the sole account when an exchange has only one connected. Saved to `spread_exec_config` via `PATCH /api/arbitrage/spread/config`.

### Changed
- **Spread Execution section** now holds only execution params; account selection moved to the Arbitrage section (single source of truth).

---

## 2026-06-27 — Show server IP for Delta API whitelisting

### Added
- **Server IP:** the Add Account form now shows the server's outbound IP (with a Copy button) in the Delta whitelist notice. `GET /api/meta/public-ip` auto-detects the IP (cached 6h) and accepts a `SERVER_PUBLIC_IP` env override.

---

## 2026-06-26 — Dashboard landing page (replaces Orders UI)

### Added
- **Dashboard:** post-login default page with portfolio-style widgets — estimated balance (cumulative or per-account scope), open positions, P&L, win rate, portfolio performance chart, asset allocation donut, ROI/statistics panels, avg holding time, and filterable trade history table. Data from account margins + `spread_trades` via `/spread/status` and `spread_execution` WebSocket.

### Removed
- **Orders UI:** `OrderTicketPage` and nav item removed; platform is no longer positioned as a manual order ticket. Backend `POST/GET /api/orders*` endpoints remain for integrators.

---

### Added
- **Spread Execution:** `SpreadExecutionService` opens delta-neutral spread trades on Delta + CoinDCX. Auto Execute picks earliest-funding / top-yield spread (50% of lower balance as margin, 10× leverage capped to both venues, auto-exits 2 min after funding). Per-card **Arbitrage** button uses 20% margin. Collections `spread_trades`, `spread_exec_config`.
- **Active Positions page:** live cards with both-leg liquidation prices, running PnL, funding inflow, auto hold countdown, manual **Close**.
- **Spreads tab:** **Auto Execute** toggle in hero; **Arbitrage** button on each coin card.
- **Account Settings:** Spread Execution section (account pair + editable margin %, leverage, hold-after-funding, liq buffer).
- **API:** `GET/PATCH/POST /api/arbitrage/spread/*`; WebSocket `spread_execution`.
- **Helpers + tests:** `spread_execution_helpers.py` (`capped_leverage`, `margin_from_balances`, `pick_auto_spread`).

### Removed
- **Arbitrage Runner:** `ArbitrageRunnerService`, runner REST routes, Runner nav/page, `arbitrage_runner` WebSocket type. `arbitrage_runner_helpers.py` retained for shared trade primitives.

---

## 2026-06-26 — Arbitrage Opportunities: cashflow, risk estimates, history & close

### Added
- **Expected cashflow:** opportunity cards show funding income per $1,000 notional (per day / year); the Execute modal shows a per-margin table ($100 / $1,000 / custom) at the effective leverage with per-8h / day / year income.
- **Fees & slippage estimate:** Execute modal estimates taker fees (Delta product rate, else 0.05%) + slippage (5 bps/side) for entry and round trip before execution.
- **Liquidation estimate:** approximate isolated-margin liquidation price for both legs in the Execute modal.
- **Funding interval alignment risk:** flags when alt and hedge legs settle on different cadences (e.g. 4h vs 8h) on cards and in the modal.
- **Basis spread warning:** Execute modal notes that long alt + short hedge is not perfectly delta-neutral.
- **Executed opportunity history:** `GET /api/arbitrage/opportunities/history` and an Executed Opportunities list in the Opportunities tab.
- **Manual close:** `POST /api/arbitrage/opportunities/close` market-closes both legs; **Close legs** button on open history rows. `opportunity_trades` now stores `accountId`.
- **Helpers + tests:** `expected_cashflow`, `cashflow_for_margin`, `trade_cost_estimate`, `liquidation_price`, `funding_interval_alignment` in `utils/opportunity_helpers.py`.

---

## 2026-06-26 — Arbitrage Opportunities tab + app shell restyle

### Added
- **Opportunities tab (Arbitrage):** scans BCH and ETC for negative funding on Delta or CoinDCX; shows a card when either venue has negative per-8h funding (displays the most negative rate). Strategy: long BCH/ETC and short equal-notional BTC/ETH on a user-selected exchange. **Execute Opportunity** modal with exchange picker, account, editable quantity/leverage, required vs available margin bar, and real limit-order execution on both legs.
- **Backend:** `OpportunityService`, `utils/opportunity_helpers.py`, `GET/POST /api/arbitrage/opportunities*`; persists to `opportunity_trades`. CoinDCX `fetch_usdt_balance` for margin quotes.

### Changed
- **App shell restyle:** white top-nav with lime accent, avatar/notifications menu, site footer, green auth panel. **Account Settings** modal reworked with sidebar (Profile, Trading Account, API) and connected-account cards matching the new visual style. CryptoBridge branding unchanged.

---

## 2026-06-26 — Arbitrage: top 6 spreads + next-funding countdown

### Changed
- **Arbitrage page now shows the top 6 coins by per-8h spread** instead of the full common-coin list (hero shows "6 / N coins"). Rendered as a responsive **Tailwind card grid** (replacing the table) — each card shows the coin, spread·8h + annualized, both venues' rate/interval/next-funding countdown, and the suggested trade.

### Added
- **Next-funding countdown per venue:** each funding cell shows a live ticking countdown (`next 2h 14m`) to that exchange's next funding settlement. Backend adds `next_funding_ts` (next UTC interval boundary) and emits `deltaNextFundingTs` / `coindcxNextFundingTs` on each funding row.

---

## 2026-06-26 — Directional Options backtest: stop-loss %

### Added
- **Stop-loss % (default 50, user-editable):** in the backtest, a short option is exited when its premium rises by this percentage above entry (`exitReason: "stop_loss"`). After a stop-out the strategy stays flat until the next Supertrend direction flip; `0` disables the stop. Threaded through `BacktestParams.stop_loss_pct`, the `POST /api/directional-options/backtest` body (`stopLossPct`), and the backtest modal form.

---

## 2026-06-26 — Directional Options: fix missing entry price & PnL

### Fixed
- **Forward-test entry premium:** opening a simulated leg no longer silently skips when the freshly-subscribed option has no WebSocket tick yet. `_open_trade` now resolves the premium via WS cache → short WS wait → **REST `fetch_ticker` fallback** (which also seeds the market cache so mark-to-market works).
- **Pending entry fill:** if no premium is available at open, the trade is created with `pendingEntry` and the entry price is filled on the first option tick (`_maybe_fill_entry`); the UI shows "Pending tick…" until then.
- **Live PnL:** added a 15s mark-to-market refresh (`_mtm_loop`) that re-prices open options (REST seed) and rebroadcasts so unrealized PnL updates even when option ticks are sparse.

---

## 2026-06-26 — Directional Options: strategy backtest

### Added
- **Backtest engine:** `utils/directional_options_backtest.py` — Black-Scholes option pricing, front-monthly (last Friday) expiry, Supertrend flip simulation, equity curve + summary stats (total/avg PnL, win rate, best/worst, max drawdown).
- **Service:** `DirectionalOptionsService.run_backtest` — chunked historical candle fetch (≤2000/req, capped at 8000), runs the engine with fully user-supplied parameters.
- **API:** `POST /api/directional-options/backtest`.
- **Frontend:** `DirectionalBacktestModal` — modal intake form for all parameters (date range, resolution, Supertrend period/multiplier, quantity, strike step, implied volatility, risk-free rate, contract value, expiry mode) with results (stat boxes, equity sparkline, trade table); **Backtest** button on `DirectionalOptionsPage`.

---

## 2026-06-25 — Directional Options Selling (simulation)

### Added
- **Supertrend helper:** `utils/supertrend.py` — Wilder-ATR Supertrend(10,2) with per-bar line value and `up`/`down` direction.
- **Candle WebSocket:** `DeltaMarketDataService` subscribes `candlestick_1h` for BTCUSD; closed bars published on `candle_broadcaster`; REST seed for ATR warmup.
- **DirectionalOptionsService:** BTC 1H Supertrend signal, monthly nearest-strike option selection, simulated short PUT/CALL flips, premium mark-to-market, Mongo persistence (`directional_options_config`, `directional_options_trades`), startup resume of enabled engines.
- **API:** `GET/PATCH/POST /api/directional-options*`; WebSocket `directional_options`.
- **Frontend:** `DirectionalOptionsPage` — testing banner, quantity, signal/Supertrend/position cards, trade history; nav **Dir. Options**.

---

## 2026-06-26 — Arbitrage Runner: automated dual-exchange execution

### Added
- **Arbitrage Runner:** `ArbitrageRunnerService` opens delta-neutral leveraged positions on top-N highest-spread coins across Delta + CoinDCX. Max leverage per venue, equal coin exposure sized to configurable margin per coin (default $10), same limit price (Delta best bid/ask). Persists trades in `arb_trades`; config in `arb_runner_config`.
- **CoinDCX trading client:** `create_futures_order`, `fetch_futures_positions`, `cancel_futures_order`, `close_futures_position`, `fetch_instrument` (cached).
- **Delta trading:** `change_leverage`, `max_leverage_for_product`.
- **Management:** liquidation-buffer exit (default 15%), spread-based coin replacement (default 20% edge), two-leg rollback on partial failure.
- **API:** `GET/PATCH/POST /api/arbitrage/runner*`; WebSocket `arbitrage_runner`.
- **Frontend:** `ArbitrageRunnerPage` — config panel (Delta + CoinDCX accounts), start/stop, running trades + fund inflow; nav item **Runner**.

---

## 2026-06-26 — Arbitrage: native funding intervals + live WebSocket updates

### Added
- **Per-instrument funding intervals:** Delta funding interval is read from `product_specs.rate_exchange_interval` (`DeltaRestClient.fetch_perpetual_funding_intervals`) — Delta perps vary (1h/4h/8h). CoinDCX `funding_frequency` is **also contract-specific** (e.g. AIOT = 4h) and is fetched per pair via `CoinDcxRestClient.fetch_funding_frequencies` (cached, concurrency-limited, only for the intersecting pairs) since it is absent from the realtime price feed. Each funding cell shows the rate at its **native interval** with an interval badge; rows carry `deltaIntervalHours` / `coindcxIntervalHours`.

### Fixed
- **Spread normalization:** Previously assumed 8h for Delta; now normalizes each venue's funding to per-8h using its actual interval (`per8h = perInterval × 8/intervalHours`) before computing spread/annualized — corrects spreads for the majority of Delta perps that fund every 4h.

### Changed
- **Live updates:** Arbitrage poll interval reduced to 15s; funding table updates stream over the `/ws/live` `arbitrage_funding` message (REST snapshot on load, WebSocket thereafter).
- **Icons:** `ExchangeIcon` brand colors tuned (Delta teal, CoinDCX navy-blue).
- **Spread display:** Spread (8h) and Annualized columns now show the **absolute magnitude** (always positive) and sort by magnitude; trade direction is conveyed by the Suggested-trade column.

---

## 2026-06-26 — Arbitrage page: visual polish + suggested-trade column

### Added
- **Arbitrage page:** New **Suggested trade** column showing Long/Short direction chips per coin (long the cheaper-funding venue, short the richer one) with branded exchange icons. New `ExchangeIcon` component renders inline Delta and CoinDCX marks.

### Changed
- **Arbitrage page:** Redesigned with a gradient hero header, summary stats (common coins, top annualized edge, normalization basis), color-coded tabular funding/spread figures, coin badges, and exchange **icons in column headers instead of names**.

---

## 2026-06-26 — Arbitrage branch: strip-down + funding-rate comparison

### Added
- **Arbitrage branch:** New `arbitrage` working branch with `backup/main-2026-06-26` preserving pre-strip `main`.
- **CoinDCX accounts:** Add-account flow supports `exchange: coindcx` with HMAC credential validation and encrypted secret storage.
- **Arbitrage Phase 1:** `ArbitrageService` polls Delta perp tickers and CoinDCX USDT futures funding, matches common coins, normalizes rates per 8h, and broadcasts `arbitrage_funding` over `/ws/live`. REST: `GET /api/arbitrage/funding`, `GET /api/arbitrage/meta`. Frontend **Arbitrage** page with sortable funding/spread table.

### Changed
- **Scope reset:** Removed charts, watchlist, planner, options, RWB, EMA Fade, Quick Order, and related backend services/tests. App is auth + accounts + manual Delta order ticket + trimmed live feed (prices + margin).
- **Orders:** Minimal explicit-quantity ticket (`POST /api/orders`); CoinDCX order routing deferred.
- **Docs:** `docs/FEATURES.md` rewritten for stripped scope and arbitrage APIs.

### Removed
- All deleted-feature routers, services, frontend pages, and tests (see plan on `arbitrage` branch).

---

## 2026-06-26 — EMA Fade backtest: restore direction filter + timeframe

### Added
- **EMA Fade backtest:** **Timeframe** selector (`1m`, `3m`, `5m`, `15m`, `30m`, `1h`; default `1m`). Sent as `timeframe` on the backtest request; candle store hydrates the chosen resolution. Included in backtest response and CSV export.

### Changed
- **EMA Fade backtest:** Restored user **Direction** (Long/Short) — only the selected side is traded. The candle-vs-EMA gate still applies (whole candle must clear the EMA on the chosen side).

---

## 2026-06-26 — EMA Fade: stricter candle-vs-EMA direction gate

### Fixed
- **EMA Fade entry rule:** direction now requires the **whole signal candle** to be on one side of the EMA — long only when the **upper wick (high) is below** the EMA, short only when the **lower wick (low) is above** it. Previously only `close` was compared to the EMA, so candles whose wick straddled the EMA (e.g. entry above the EMA on a long) were wrongly taken.

### Changed
- **Backtest:** direction is now **fully EMA-driven** (takes both longs and shorts); the modal's Direction selector is informational. Replaced `side_from_close_vs_ema(close, ema)` with `side_from_candle_vs_ema(high, low, ema)` in the engine and removed the chosen-direction filter from the backtest.
- **Live:** applies the same candle-vs-EMA gate (reject reason `ema_intersects_candle`); per-session direction scoping is unchanged.

---

## 2026-06-26 — Backtest Scalper Offer (waive closing fee)

### Added
- **RWB & EMA Fade backtests:** New **Apply Scalper Offer** toggle (sent as `scalperOffer`, default off) mirroring Delta's Scalper Program. When a position is **closed within the scalper window of entry**, the **closing-leg fee is waived** (the opening fee still applies). Window is **30 min for BTCUSD/ETHUSD**, **15 min for other futures**, evaluated **per exit leg** so partial exits qualify independently.

### Changed
- **Engines:** `RwbConfig`/`EmaFadeConfig` gain `scalper_offer`; `taker_fee()` accepts `waive_exit`; added `scalper_window_seconds(symbol)`. Routers accept `scalperOffer`.

---

## 2026-06-26 — Backtest trading fees (Delta taker + GST)

### Added
- **RWB & EMA Fade backtests:** Apply Delta's **taker fee** on every fill (entry and each exit leg). Fee = `taker_rate × notional` (`notional = contracts × contract_value × price`) using the product's `taker_commission_rate` (BTCUSD futures ≈ 0.05%), plus **18% GST**. Backtest PnL is now **net of fees**.
- **Results/CSV:** New **Total fees** and **Gross PnL** summary cards, per-trade **Fees**/**Gross PnL** detail, and corresponding CSV columns.

### Changed
- **Engines:** `RwbConfig`/`EmaFadeConfig` gain `taker_fee_rate` + `gst_rate`; `ClosedTrade` carries `fee` and `gross_pnl`; backtest services seed the taker rate from product metadata and emit `totalFees`/`grossPnl`. Live execution PnL is unaffected.

---

## 2026-06-25 — RWB backtest: EMA direction rule + EMA column

### Added
- **RWB backtest:** Signal direction is now set by **price vs EMA** — close below the EMA goes long, above goes short (close on the EMA is skipped). EMA period defaults to **5** and is editable on the backtest form.
- **RWB backtest results:** New **EMA** column in the trades table and CSV export, plus the EMA price in each trade's detail view.
- **API:** `/api/rwb/backtest/run` accepts `emaPeriod`; `/api/rwb/meta` exposes `emaDefault`.

### Changed
- **RWB backtest engine:** `simulate` computes the EMA series and overrides the pattern's natural side with the EMA rule. `ClosedTrade` / trade output carry `emaPrice`. Live RWB execution is unchanged.

---

## 2026-06-25 — EMA Fade: remember backtest inputs

### Added
- **EMA Fade backtest form:** Entered inputs are now saved locally (`localStorage`, key `emaFadeBacktestForm`) so they survive closing/reopening the modal and in-app navigation. A **page reload (hard refresh) clears** the saved inputs and resets to defaults.

---

## 2026-06-25 — EMA Fade: restore T1/T2 ladder; backtest max-SL cap

### Changed
- **EMA Fade ladder:** Restored **T1/T2** profit booking (default **20R** books **40%**, **30R** books remainder). Removed the single 50R book rung and optional target price.
- **Backtest:** Now **stops taking new trades** once `maxStopLosses` real stop-outs occur (breakeven stops don't count), matching live execution. **End time** (IST) on backtest form is retained.

### Removed
- **EMA Fade:** `bookR` / `bookFraction` / `targetPrice` fields and `book` / `target` exit reasons (reverted to `t1` / `t2`).

---

## 2026-06-25 — EMA Fade: target price + 50R book ladder (reverted)

### Changed
- **EMA Fade ladder:** Replaced T1/T2 R rungs with a single **book rung** (default **50R**, books **70%**). The remainder rides to an optional **target price** set by the user; live execution **stops automatically** when the target leg fully exits.
- **Backtest:** Added **end time** (IST) alongside end date; defaults to 23:59 when omitted.
- **API / session doc:** `t1R`/`t1Fraction`/`t2R`/`t2Fraction` replaced by `bookR`, `bookFraction`, `targetPrice`; exit reasons `book` and `target` replace `t1`/`t2`.
- **Frontend:** Start + backtest modals expose book rung, book %, and optional target price; backtest form adds end time. Session status, history, results, and CSV export updated.

---

## 2026-06-25 — RWB: replace pending entry on a better same-direction setup

### Added
- **RWB:** While an entry order is pending (unfilled), a newly detected **same-direction** setup at a **better price** (lower entry for long, higher entry for short) now cancels the live order and re-places at the new entry/stop, resetting the fill timeout. Opposite-direction setups remain ignored, as do same-direction setups at a worse or equal price.

---

## 2026-06-25 — Stop entries fill at market (remove maker/taker confusion)

### Fixed
- **All `SL` orders are now stop-market, not stop-limit.** Entry stops (RWB, EMA Fade, Planner, Quick Order) previously placed a stop-**limit** at the trigger price, which rested as a maker and could miss fast moves through the trigger. They now trigger a market order that fills immediately (taker), matching the fee model that already treated `SL` as taker.
- **Fallback protective stop** (`place_stop_order`) switched from stop-limit to stop-market, aligning it with the native position brackets so a triggered stop always fills.

---

## 2026-06-25 — EMA Fade: manual direction + R ladder (BTC only)

### Changed
- **EMA Fade:** Now **BTCUSD only** and **manual directional** — user picks LONG or SHORT at start; the EMA still computes each signal's side, but only signals matching the chosen direction are taken.
- **Target ladder (editable):** 6R moves stop to breakeven (no booking); 20R books 40%; 30R books remaining 60%, after which execution **stops automatically** (win).
- **Stop-loss budget:** user-defined **max stop losses** — real stop-outs (before breakeven) count; reaching the limit **stops execution automatically**. Breakeven stops don't count.
- **Session doc / view:** added `direction`, `maxStopLosses`, `stopLossCount`, `breakevenR`, `t1R`/`t1Fraction`, `t2R`/`t2Fraction`; removed `target1R`/`target2`.
- **API:** `/api/ema-fade/backtest/run` and `/sessions/start` accept `direction`, `maxStopLosses`, `breakevenR`, `t1R`, `t1Fraction`, `t2R`, `t2Fraction` (BTCUSD enforced); `meta` exposes the new defaults.
- **Frontend:** start + backtest modals add Direction, Max stop losses, Breakeven (R), and editable T1/T2 R + book %; symbol locked to BTCUSD. Session status and CSV export reflect the new ladder.

---

## 2026-06-25 — EMA Fade strategy

### Added
- **EMA Fade:** Clone of RWB with EMA-based side selection — hammer/shooting star + C1/C2/C3 filter; close below EMA → long, above → short; editable EMA period (default 9), T1 (default 6R), T2 (default 20R).
- **Backend:** `/api/ema-fade` routes, `ema_fade_sessions` Mongo collection, `ema_fade_session` WebSocket updates, shared execution with `emaf` order prefix.
- **Frontend:** **EMA Fade** nav page (Live / History / Backtest); backtest table and CSV export include EMA price column.

---

## 2026-06-24 — Rejection Wick Breakout + candle store

### Added
- **Rejection Wick Breakout (RWB):** Hammer/shooting star 1m structure break strategy — backtest from start date/time, optional live deployment, lots or max-risk sizing, 50% @ 6R + remainder @ 20R.
- **Candle store:** Tick → M1 builder, Mongo `candle_bars` persistence, Delta hydration for missing history.
- **Candle detector API:** `POST /api/orders/candle-detector/preview` (powers existing Order Screen modal).
- **Frontend:** **Wick Break** nav page with Live / History / Backtest tabs.

---

## 2026-06-24 — Open Break Writer backtest

### Added
- **Open Break Writer (OBW):** Backtest strategy — mark session open at 18:30 IST, sell OTM call/put on configurable upside/downside breaks, ITM/ATM/OTM strike offset, SL/TP rules.
- **Backend:** `POST /api/options/backtest/run`, historical expired options + candle data from Delta.
- **Frontend:** Options page **Backtest** tab with form and results summary.

---

## 2026-06-24 — Options live price refresh + PnL card layout

### Fixed
- **Options:** Live premiums, spot, and PnL cards update continuously — backend broadcasts every market tick (no session-wide throttle skip), frontend prefers fresh WS/REST quotes over stale session fields, and polls `/api/options/quotes` every 2s as fallback.
- **Options UI:** PnL panel uses a 6-column equal-width grid (Entry Premium, Spot, Mark Premium, Running/Booked/Total PnL).

---

## 2026-06-24 — Configurable options underlying + session spot

### Added
- **Options:** `GET /api/options/underlyings` — lists underlyings with today's 0DTE option chain (fallback: BTC, ETH, SOL).
- **Options UI:** Underlying selector when starting a short strangle (BTC, ETH, and other Delta underlyings).
- **Options UI:** Live underlying spot between Entry Premium and Mark Premium on the PnL panel.

### Changed
- **Options:** Strategy page title, strike preview, and session status reflect the configured underlying instead of hardcoded BTC.

---

## 2026-06-24 — Strangle live price/PnL + header BTC spot

### Fixed
- **Options:** Leg live premiums and Mark Premium / Running PnL update again after backend restart — option leg symbols and `BTCUSD` are re-subscribed on session restore via Delta market WS.
- **Options:** Theoretical PnL for `selected` / `entry_placed` legs (picked premium vs live) is included in session metrics and the PnL panel before fill.
- **Options UI:** Live leg table and PnL totals fall back to global `type: price` ticks when `options_strategy` payloads lag.

### Changed
- **Header:** Shows live `BTC {price}` from `BTCUSD` watchlist ticks next to the connection badge.

---

## 2026-06-24 — Options strategy duplicate orders

### Fixed
- **Options:** Prevent duplicate entry/SL orders on backend restart — idempotent strike selection and order placement, persist leg state after each order, recover session state from saved leg progress, per-session runner lock, broker order reconciliation via `client_order_id`, one state transition per runner loop, serialized session start per user.

---

## 2026-06-24 — Options strategy lot sizing

### Fixed
- **Options:** Order `size` now uses the configured lot count directly (e.g. 100 lots → size 100 on Delta). Previously multiplied lots by `contract_value` (0.001) and clamped to 1, so 100 lots became 1.

---

## 2026-06-24 — Options entry countdown

### Changed
- **Options:** Entry wait countdown ticks every second on the client and displays `hh:mm:ss` (IST) instead of a static seconds value from the server.

---

## 2026-06-22 — BTC Options Short Strangle

### Added
- **Options strategy:** Automated BTC 0DTE short strangle — timed entry (default 1:30 PM IST), premium-based strike pick (>62, closest ATM), stop-sell entry at `ceil(premium−2)`, 60% SL after fill, 5:00 PM exit.
- **Backend:** Option chain API, strike preview, strategy runner with activity log, running/booked PnL, live CE/PE premiums via WS.
- **Frontend:** **Options** page with strategy config, live leg prices, PnL panel, and activity feed.

---

## 2026-06-22 — Production API at crypto.api.signalbridge.in

### Changed
- **Frontend:** Default API/WS to `https://crypto.api.signalbridge.in` via `.env` and `src/config/endpoints.js`; fixed `wss://` for HTTPS WebSockets.
- **Backend:** `PUBLIC_API_BASE_URL`, `CORS_ALLOWED_ORIGINS` for `https://crypto.signalbridge.in`; health returns `publicApiBaseUrl`.

---

## 2026-06-22 — Public IP / LAN access

### Changed
- **CORS:** Configurable `CORS_ALLOW_ORIGIN_REGEX` allows access from public and LAN IPs (not just localhost/private ranges).
- **Frontend:** API/WebSocket base URL follows the browser hostname when `VITE_API_BASE` is unset.
- **Scripts:** `run-backend` prints LAN/public access URLs on start/status.

---

## 2026-06-22 — Simplify run scripts

### Changed
- **Scripts:** Only `scripts/run-backend.sh` and `scripts/run-backend.bat` remain. Setup, health check, and lifecycle are built in. Removed `run-servers.sh`, `setup-backend.*`, `health-backend.*`.
- **Docs:** README and project-context updated for separate backend/frontend start.

---

## 2026-06-22 — Docs, backend scripts, public IP, retryable orders

### Added
- **Scripts:** `scripts/run-backend.sh` and `scripts/run-backend.bat` — start Python backend only (relative paths, no absolute paths).
- **Public IP:** `GET /api/meta/public-ip` returns server outbound IP for Delta API key whitelisting; shown with copy button in Manage Account modal.
- **Retryable orders:** LIMIT stop-out → one SL retry; SL stop-out → one SL re-place. Applies to Trade (LIMIT + SL) and Quick Order (`retryableOrder`, default on).
- **Order economics:** Quantity labels (`0.32 BTC / 320 lots`), required margin, and estimated fees in preview (`TradeEconomics`, `order_economics.py`).

### Changed
- **Quick Order:** Form moved into modal; history on main page; retryable checkbox.
- **Planner:** Create plan modal no longer resets on live price ticks; symbol picker is a watchlist `<select>`.
- **Trade:** Retryable order checkbox enabled for SL orders (not LIMIT only).
- **Docs:** Updated FEATURES, README, project-context, FRONTEND_SMOKE.

---

## 2026-06-22 — Max risk cap rule ($10 / 1%)

### Changed
- **Max risk:** `$10` when available margin `< $1,000`; otherwise **1%** of available margin (replaces prior 10% cap).
- **Backend:** New `utils/risk_limits.py`; enforced in Quick Order, order placement, risk preview, and planner start.
- **Frontend:** Shared `utils/riskLimits.js`; validation in Quick Order, order ticket, planner create modal.
- **Docs:** Updated [FEATURES.md](./FEATURES.md) §11, smoke checklist.

---

## 2026-06-22 — Tick-size price precision (BTC/ETH/SOL and all products)

### Changed
- **Price precision:** Decimal places now derive from Delta product `tick_size` (e.g. `0.01` → 2 digits, `0.001` → 3 digits), not from the current live price.
- **Backend:** New `utils/price_precision.py`; `InstrumentCatalogService` caches tick sizes for all live products; watchlist stores `priceDigits` + `tickSize`; snapshots and WS `price` ticks include correct `price_digits`.
- **Frontend:** Removed hardcoded symbol precision in chart/watchlist; shared `resolvePriceDigitsForSymbol()`; suggest API returns `price_digits` per instrument.
- **Docs:** Added [FEATURES.md](./FEATURES.md) §10, [CHANGELOG.md](./CHANGELOG.md), [DOCUMENTATION-POLICY.md](./DOCUMENTATION-POLICY.md).

---

## 2026-06-22 — Available margin display & wallet enrichment

### Fixed
- **Wallet parsing:** Prefer USD/USDT/INR wallet rows; fall back to `meta.net_equity` when per-asset balance is zero.
- **Quick Order:** Risk cap uses `effective_available_margin()` (margin or net equity).
- **Errors:** Wallet fetch failures set `walletError` on account; logged server-side.

### Changed
- **Header:** “Avail …” margin shown on all screen sizes; mobile account menu shows margin; account dropdown shows margin in brackets.
- **Quick Order:** Prominent available-margin card with 10% max risk hint.
- **Manage Account:** Always shows margin or “unavailable”.
- **Frontend:** New `utils/accountMargin.js`.

---

## 2026-06-22 — Quick Order flow

### Added
- **Page:** Quick Order (`currentPage: quick-order`) in header navigation.
- **API:** `GET/POST /api/quick-orders`, `POST /api/quick-orders/preview`.
- **Backend:** `QuickOrderService` — candle entry/SL from completed bars, 10% margin risk cap, Mongo `quick_orders`, 12s status/P/L sync, WS `quick_order` events.
- **Utils:** `utils/candle_levels.py` — nth completed candle, entry/SL ± 1 tick.
- **UI:** `QuickOrderForm`, `QuickOrderHistory`, `SymbolSearchBox` with keyboard navigation and watchlist auto-subscribe.

---

## 2026-06-22 — Crypto Planner enhancements

### Added / Changed
- **UI:** Dedicated Planner page with watchlist sidebar; list all plans; Create plan modal; collapsible plan cards with activity log.
- **Per-plan risk:** `plannerRiskAmount` on account (Mongo); persisted via `PATCH /api/accounts/{id}/planner-risk`.
- **Stop flow:** `POST /api/planner/stop` with `sessionId` + optional `closePosition`.
- **API:** `GET /api/planner` (all sessions), activities on session view.
- **Pivot UX:** Blank pivot ≠ 0; direction/trap UI only when pivot and mark are known.

---

## 2026-06-22 — Mandatory risk-based quantity

### Changed
- **Order placement:** `OrderService.place()` always computes size from `risk_amount` + entry/SL; ignores client `size`.
- **Shared:** `utils/risk_sizing.py` used by risk preview, planner entry, quick orders.
- **Tests:** `tests/test_risk_sizing.py`.

---

## 2026-06-22 — Forex removal & watchlist defaults

### Removed
- EURUSD / forex-specific UI (`flag-icons`, forex filters).
- Default symbol EURUSD on order screen.

### Changed
- **Watchlist defaults:** `BTCUSD`, `ETHUSD`, `SOLUSD`.
- **WatchlistService:** `purge_invalid_symbols()` removes symbols not on Delta; runs on dashboard/WS connect and account add/select.
- **Symbol resolve:** 404 when Delta returns `result: null` (invalid symbols).

---

## Earlier (v0.1 baseline)

### Added
- Local auth (register/login, 7-day session tokens).
- Delta account onboarding (`GET /v2/profile` validation, encrypted secrets).
- Watchlist CRUD with live Delta public WebSocket prices.
- MT5-style trading workspace (watchlist, chart, order ticket).
- OHLC charts via `GET /v2/history/candles`.
- Market/limit/SL orders with bracket TP/SL; cancel pending.
- Multi-account risk preview and copy trading (up to 2 accounts).
- Crypto Planner pivot strategy (backend state machine, 1m candles).
- Dashboard snapshot + `/ws/live` multiplexed stream.
- Header: balance, margin, running P/L, account management modal.
- Python FastAPI backend as default (`run-servers.sh`); Java WebFlux retained as legacy reference.

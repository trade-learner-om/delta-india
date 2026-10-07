# Frontend smoke checklist

Manual regression after backend or frontend changes.  
Full feature list: [docs/FEATURES.md](../docs/FEATURES.md)

## Auth & accounts

- [ ] Register new user — login works, token in localStorage; login panel shows **CryptoBridge SVG logo** (not "CB" text)
- [ ] Add Delta account — profile validates; account appears in selector
- [ ] **Public IP** visible in Manage Account with Copy button (server outbound IP for Delta whitelist)
- [ ] **Available margin** visible in header (“Avail …”), account dropdown `(amount USD)`, Manage Account modal, Quick Order margin card
- [ ] Select / switch account — dashboard refreshes, watchlist defaults seed if empty
- [ ] Delete account — removed from list; selection moves to next account
- [ ] Edit master risk on order ticket — saves on blur; persists after refresh
- [ ] Edit planner risk in Create plan modal — persists after refresh

## Watchlist & prices

- [ ] Default watchlist: BTCUSD, ETHUSD, SOLUSD on first account setup
- [ ] Add symbol via suggest — appears in watchlist; live price updates (WS)
- [ ] Remove symbol — disappears; chart clears if it was selected
- [ ] Invalid / forex symbol rejected with clear error
- [ ] **Price precision:** BTC/ETH show **2** decimals; SOL shows **3** decimals in watchlist, chart, order ticket

## Trading page

- [ ] Chart loads candles; timeframe switch works
- [ ] Live tick updates current bar
- [ ] Order ticket: symbol from watchlist; MARKET fills entry from bid/ask
- [ ] Risk preview shows quantity per selected account; rejects risk above max cap
- [ ] Place LIMIT/SL order — appears in Positions; cancel works
- [ ] **Retryable order** checkbox for LIMIT and SL; one retry after stop-out
- [ ] Copy trade (2 accounts) — placement summary shows success/fail counts
- [ ] Candle Detector modal populates entry/SL/side

## Quick Order page

- [ ] Available margin card shows balance; max risk = **$10** if margin &lt; $1,000, else **1%** of margin
- [ ] Symbol search (arrows + Enter); subscribes symbol to watchlist if missing
- [ ] Preview shows entry, SL, quantity with correct decimals
- [ ] Place order — appears in history; WS updates status/P/L
- [ ] **Retryable order** checkbox (default on); shows retry used in history when applicable
- [ ] Risk above max cap rejected in preview (e.g. $15 risk on $500 margin)

## Planner page

- [ ] Create plan — max risk validated ($10 below $1k margin, else 1%)
- [ ] Create plan — symbol dropdown lists watchlist instruments; form fields do not reset while typing
- [ ] Create plan — session appears with direction from pivot vs mark
- [ ] Trap checkbox only when pivot + mark known
- [ ] Plan card shows pivot, levels, activities; stop plan works
- [ ] Stop with open position — modal offers close position option
- [ ] WS updates plan status without full page reload

## Positions page

- [ ] Open orders listed; cancel pending order works

## Active Positions payoff

- [ ] Close an option leg on the Delta broker UI while the app is open — **Active Positions** drops that row within ~2s (WS) or ≤15s (REST fallback)
- [ ] Select one or more open legs sharing the same underlying → generic payoff curve renders (no calendar auto-detection)
- [ ] Mixed underlyings selected → sensible empty message

## Live / dashboard

- [ ] Dashboard snapshot — `GET /api/dashboard` and WS initial `snapshot` match header state
- [ ] Connection badge: connected after load; reconnects after backend restart
- [ ] `running_pl` in header matches open positions on Delta (approximate)

## Execution page (spot SL engine)

- [ ] Nav shows **Dashboard**, **Execution**, **ST Options**, and **Active Positions**
- [ ] Execution: search BTC/ETH options (strike ascending), sell lots, entry spot + spot SL inputs
- [ ] Margin preview shows required vs available
- [ ] **Execute & Monitor** creates monitor in `Pending Trigger`; table updates via WS `execution_monitor`
- [ ] Safe Mode badge when spot feed disconnects on filled monitor

## ST Options (1H SuperTrend sell)

- [ ] Nav **ST Options** opens Live (Running | History) + Backtest tabs
- [ ] Running: compact Strategy on/off + **gear** opens Strategy settings modal with **Max risk ($)** / **Stop loss %** / **Take profit %** / **Max close→ST distance %** / **Hedge after decay %** (0 = off); Turn on / Turn off on the page
- [ ] While strategy is on, settings stay locked except **Hedge after decay %** (can arm/disarm mid-run; open hedge left if set to 0); Save persists and applies immediately; editing the field is not wiped by Market watch WS updates
- [ ] Advanced (Live modal + Backtest gear) shows confirm warn (“not recommended”) before ST/EMA fields
- [ ] No risk footnote on Running; no lonely empty card while on and flat
- [ ] Market watch: opposite side shows “Not active while bias is down/up”; active side keeps bounce/ready copy
- [ ] Running: Strategy card shows Total PnL; settings include **Move SL to BE after decay %** (default 40, 0 = off)
- [ ] Live Running: header shows As of / Bias (clear up/down arrow) / Market from live WS spot (not only 1H bar close)
- [ ] Running: compact live summary boxes (trades, Long/Short closed counts, profit/loss counts, max/total P&L, loss-to-profit)
- [ ] Market watch: Bias as SVG arrow; Updates timestamps in IST; loss closes red + bold result lines
- [ ] After configured premium decay, Protect-at moves to entry (breakeven); Updates notes the move
- [ ] Live hedge: after main melts hedge %, opposite short opens; Running card shows main | hedge side-by-side with hedge Protect at (frozen); combined PnL below; target/stop/hedge-SL/max-loss exit both; History may show main + hedge rows with shared pair
- [ ] Live Running page has soft green (bias up) / red (bias down) wash
- [ ] Market watch shows phase, readiness, Checks again in m:ss, Updates (`userMessage` only)
- [ ] If off with leftovers: leftover panel + **Close positions**; after no-contract failure, **Force close** (confirm) clears the record
- [ ] History exit reasons: Market flipped / Stop / Target / Closed manually / Closed before expiry / Settled at expiry / Force closed / Max loss / Pair exit
- [ ] Operators: server log lines prefixed `ST Options:` on start/stop/bar/open/close/skip/settle
- [ ] Open Long-side and Short-side cards can appear together; History lists closed trades with Side / Bias icon / Reason / Result
- [ ] Backtest: From/To outside (default today−7…today IST) + gear settings (Max risk $, SL/TP/BE + strike mode + formation + skip-after-Target + max close→ST distance % + dyn % sizing) → Run; progress via WS; summary KPIs include wins/losses, streak `4(2)`, averages; Quantity column varies with premium/SL/risk
- [ ] Backtest has **Max risk ($)** (same as live); changing SL % or max risk changes lot sizes
- [ ] Dynamic sizing: Add % / Reduce % / Max risk % of base (not lot counts); after losses risk budget steps by % of base maxRisk then lots recompute
- [ ] Backtest strike modes: **Strike type** shows moneyness only (no expiry select; hint about 05:30 rule); **Min %** shows % input; **SuperTrend** no extra inputs; **Minimum premium** shows absolute input — only one mode active
- [ ] One trade per formation (on): after TP/SL/flip exit, same side does not re-enter until ST colour flips; (off): TP re-entry still allowed
- [ ] Skip next setup after Target (default 1): after take-profit only, next N signals on that side are skipped; 0 = off; Long/Short independent; works with formation gate
- [ ] Max close→ST distance % (default 0.3): live + backtest skip entries with |close−ST|/close ≥ threshold; 0 = off; Market watch shows “nearer the SuperTrend line” when geometry is ready but distance fails
- [ ] Pair hedge off: single-leg as before. On + Immediate: both legs open; exit on PE≈CE or main SL. On + After decay: hedge opens after % melt; both exit on main TP/SL
- [ ] Running cards / History / Backtest / Dashboard Recent Trades show Quantity (lots)
- [ ] Backtest settings persist separately from live; completed run appears in Saved runs; reloading a run restores result and stays selected (does not snap back to latest on live WS updates)
- [ ] Compare (≥2 saved runs): input diffs, overlapping trades only, % PnL after lot normalize, verdict, Download PDF with CryptoBridge branding
- [ ] Backtest SL/TP inputs change results: raising TP % (e.g. 50) books earlier; lowering SL % (e.g. 50) stops earlier
- [ ] Backtest with 0 trades shows diagnostics note (signals / skipped no premium or no contract); SL copy is entry + 105% (2.05×)
- [ ] ~30d backtest finishes in tens of seconds (not multi-minute) under normal Delta latency
- [ ] Live entries: ATM±1 only; ticker volume must be **above the band average**; skip “no liquid strike (ATM±1)” if none; same-day only ≤10:30 IST; never farther than T1
- [ ] Live entry is **limit sell at mark−1** (not market); lots sized from that limit + Stop loss % **with 40% slippage buffer** + Max risk; skip if 1 lot would exceed max risk; unfilled limit **cancels quickly** (not a 20-minute leftover)
- [ ] Live entry attaches broker **stop-market** stop-loss and take-profit (trigger only, no limit cap) at the configured premium levels; active card shows matching Protect at / Target values
- [ ] Unhedged Running trade whose live PnL reaches **−maxRisk** flattens (`max_loss`) even if broker SL is still working
- [ ] Broker SL/TP fill closes the trade once in History; an ST flip cancels both pending bracket legs before market exit
- [ ] If broker bracket attachment fails, Updates warns the user and soft premium monitoring still enforces the configured levels
- [ ] Limit entry: if fill races cancel, Running still shows the trade and broker SL/TP attach (no naked short); pending_entry shows “confirming entry” briefly
- [ ] Limit cancel 404 while still PENDING: Updates says **Limit cancelled — setup skipped** (not “still watching for fill”); leftover limit is not left on the book
- [ ] Naked short on Delta with engine on and no ST card: next tick adopts it and attaches stop/target
- [ ] Running card Bias shows up/down arrow (not “—”), including for adopted shorts
- [ ] Running card shows Open (est.), Est. loss (stop), Est. profit (target)
- [ ] If SL/TP already exist on Delta (manual), ST links them (“Linked existing stop/target”) instead of “could not be attached”
- [ ] Updates panel uses remaining vertical space on Running; insufficient-margin skips show need/available $ in Updates
- [ ] Running: footer stays visible (no page-level scrollbar from Updates stretch); taller History/Backtest scrolls inside main
- [ ] History: first page of 20 closed trades in a capped scroll table; **Showing X of Y** + **Load more** when more exist; Running Total PnL / summary strip use full closed `summary` (not page-only)
- [ ] Closing a short on Delta (outside ST) moves the trade to History with fill-based PnL within ~one engine tick
- [ ] Same-day opens square off at 17:15 IST; past settlement cannot stay stuck open

## Execution Terminal (Dashboard + Active Positions)

- [ ] Dashboard loads accounts, KPIs, Equity Performance Wave from closed ST Options, Recent Trades (square-off IST + PnL), positions preview
- [ ] Active Positions: open ledger, history, payoff tab; WS `positions` updates
- [ ] Terminal state derives `watchList` from live prices + open positions; `fsmEngines` from open positions

## Workspace shell & navigation

- [ ] Footer live status stays **Connected** without flapping while idle (ping/pong keeps the socket alive; no reconnect storm in server logs)
- [ ] Logout / page navigation does not leave orphan `/ws/live` reconnect timers
- [ ] Auth failure (`1008`) clears the session instead of reconnecting forever
- [ ] Default **dark** theme on first visit; preference persists after refresh (`cryptobridge.theme` in localStorage)
- [ ] Theme toggle in header switches light/dark; charts and cards follow theme tokens
- [ ] Nav badge: position count on **Active Positions**; active monitor count on **Execution**; open ST Options count on **ST Options**

"""Pure backtest loop for 1H ST Options (injectable candle / premium sources)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from cryptobridge.utils.st_options_indicators import IndicatorBar, OhlcBar, compute_indicator_bars
from cryptobridge.utils.st_options_pair_hedge import pair_premiums_equal, should_open_decay_hedge
from cryptobridge.utils.st_options_resolver import (
    Direction,
    ResolvedOption,
    bar_close_unix,
    contract_value_for,
    force_close_cutoff_unix,
    format_ist,
    parse_option_symbol_expiry,
    resolve_option_waterfall,
)
from cryptobridge.utils.st_options_strategy import (
    DEFAULT_BREAKEVEN_DECAY_PCT,
    DEFAULT_EMA_LENGTH,
    DEFAULT_MIN_PREMIUM_PCT,
    DEFAULT_QUANTITY,
    DEFAULT_ST_MULTIPLIER,
    DEFAULT_ST_PERIOD,
    DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT,
    ExitReason,
    build_entry_signal,
    entry_ready,
    evaluate_premium_brackets,
    opposite_st_exit,
    should_move_sl_to_breakeven,
    short_option_pnl,
)

IST = ZoneInfo("Asia/Kolkata")


def formation_blocks_entry(
    *,
    enabled: bool,
    blocked_colour: str | None,
    current_colour: str | None,
) -> bool:
    """True when one-trade-per-formation blocks a new entry on this side."""
    if not enabled or blocked_colour is None:
        return False
    return (current_colour or "") == blocked_colour


def clear_formation_block(
    *,
    blocked_colour: str | None,
    current_colour: str | None,
) -> str | None:
    """Clear blocked colour once ST colour has changed."""
    if blocked_colour is None:
        return None
    if (current_colour or "") != blocked_colour:
        return None
    return blocked_colour


def arm_skip_after_take_profit(*, exit_reason: str, skip_n: int) -> int | None:
    """After a take_profit exit, return the skip counter to arm; else None (unchanged)."""
    if exit_reason == "take_profit" and skip_n > 0:
        return int(skip_n)
    return None


def consume_skip_setup(skip_left: int) -> tuple[bool, int]:
    """If skip_left > 0, skip this entry signal and decrement; else do not skip."""
    left = int(skip_left)
    if left > 0:
        return True, left - 1
    return False, left


PremiumLookup = Callable[[str, Any, float, str], Optional[float]]
OptionCandleLookup = Callable[[str, int], tuple[Optional[float], Optional[float], Optional[float]]]


@dataclass
class OpenTrade:
    direction: Direction
    entry_time: int
    st_colour: str
    st_colour_change_time: int | None
    ema_price: float
    strike: float
    expiry: str
    option_symbol: str
    premium_received: float
    contract_value: float
    lots: int
    allow_reentry_after_tp: bool = False
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT
    breakeven_decay_pct: float = DEFAULT_BREAKEVEN_DECAY_PCT
    sl_moved_to_breakeven: bool = False
    # Pair hedge (same-strike opposite); attached to main side only.
    pair_id: str | None = None
    pair_hedge_mode: str | None = None  # immediate | on_decay
    pair_hedge_decay_pct: float = 40.0
    main_option_side: str | None = None  # PUT | CALL
    hedge_symbol: str | None = None
    hedge_premium_received: float | None = None
    hedge_entry_time: int | None = None
    hedge_pending: bool = False


@dataclass
class ClosedTrade:
    date: str
    direction: Direction
    st_colour: str
    st_colour_change_time: str | None
    ema_price: float
    strike: float
    expiry_date: str
    premium_received: float
    exit_price: float
    exit_reason: ExitReason
    pnl: float
    entry_time: int
    exit_time: int
    option_symbol: str
    lots: int = 1
    pair_id: str | None = None
    leg_role: str | None = None  # main | hedge


@dataclass
class BacktestSummary:
    total_trades: int = 0
    total_pnl: float = 0.0
    long_trades: int = 0
    short_trades: int = 0
    long_pnl: float = 0.0
    short_pnl: float = 0.0
    max_profit: float | None = None
    max_profit_date: str | None = None
    max_loss: float | None = None
    max_loss_date: str | None = None
    max_drawdown: float = 0.0
    max_dd_from: str | None = None
    max_dd_to: str | None = None
    win_count: int = 0
    loss_count: int = 0
    max_win_streak_len: int = 0
    max_win_streak_count: int = 0
    max_loss_streak_len: int = 0
    max_loss_streak_count: int = 0
    avg_profit: float | None = None
    avg_loss: float | None = None


@dataclass
class DynamicSizingConfig:
    enabled: bool = False
    after_losses: int = 2
    increase_pct: float = 10.0
    max_risk_pct: float = 200.0
    after_profits: int = 2
    decrease_pct: float = 10.0


def lots_from_max_risk(
    max_risk: float,
    entry_premium: float,
    stop_loss_pct: float,
    contract_value: float,
) -> int:
    """Lots so that SL loss ≈ max_risk: premium × (SL%/100) × cv × lots."""
    risk = float(max_risk)
    prem = float(entry_premium)
    sl = float(stop_loss_pct)
    cv = float(contract_value)
    if risk <= 0 or prem <= 0 or sl <= 0 or cv <= 0:
        return 1
    risk_per_lot = prem * (sl / 100.0) * cv
    if risk_per_lot <= 0:
        return 1
    return max(1, int(risk / risk_per_lot))


# Live entry: aggressive sell limit relative to mark/last (USD premium points).
ENTRY_LIMIT_OFFSET = -1.0
# Live lot sizing treats SL distance as this % wider so stop-market slippage stays near maxRisk.
LIVE_SL_SLIPPAGE_BUFFER_PCT = 40.0
LIVE_STRIKE_DEPTH = 1  # ATM ±1 (OTM1 / ATM / ITM1)


def entry_limit_price(current_premium: float, *, offset: float = ENTRY_LIMIT_OFFSET) -> float | None:
    """Limit sell price from live mark/last. None if invalid."""
    current = float(current_premium)
    if current <= 0:
        return None
    limit = current + float(offset)
    if limit <= 0:
        return None
    return limit


def risk_per_lot(
    entry_premium: float,
    stop_loss_pct: float,
    contract_value: float,
) -> float:
    """Dollar SL risk for one lot at entry premium."""
    return float(entry_premium) * (float(stop_loss_pct) / 100.0) * float(contract_value)


def lots_from_max_risk_or_none(
    max_risk: float,
    entry_premium: float,
    stop_loss_pct: float,
    contract_value: float,
    *,
    slippage_buffer_pct: float = 0.0,
) -> int | None:
    """Like lots_from_max_risk, but None when even 1 lot would exceed max_risk.

    ``slippage_buffer_pct`` widens the SL% used for sizing (live stop-market fill
    can overshoot the trigger). Backtest leaves this at 0.
    """
    risk = float(max_risk)
    prem = float(entry_premium)
    sl = float(stop_loss_pct) * (1.0 + max(0.0, float(slippage_buffer_pct)) / 100.0)
    cv = float(contract_value)
    if risk <= 0 or prem <= 0 or sl <= 0 or cv <= 0:
        return None
    per_lot = risk_per_lot(prem, sl, cv)
    if per_lot <= 0:
        return None
    if per_lot > risk:
        return None
    return max(1, int(risk / per_lot))


@dataclass
class DynamicSizingState:
    """Shared consecutive-streak risk-budget sizing for backtest (both sides).

    Budget moves in additive steps of base maxRisk × pct/100 (not compound).
    Lots are recomputed from current budget + entry premium on each entry.
    """

    config: DynamicSizingConfig
    initial_risk: float
    current_risk: float
    loss_streak: int = 0
    win_streak: int = 0

    @classmethod
    def create(cls, initial_risk: float, config: DynamicSizingConfig | None = None) -> DynamicSizingState:
        cfg = config or DynamicSizingConfig()
        base = max(0.0, float(initial_risk))
        max_pct = max(100.0, float(cfg.max_risk_pct))
        return cls(
            config=DynamicSizingConfig(
                enabled=bool(cfg.enabled),
                after_losses=max(0, int(cfg.after_losses)),
                increase_pct=max(0.0, float(cfg.increase_pct)),
                max_risk_pct=max_pct,
                after_profits=max(0, int(cfg.after_profits)),
                decrease_pct=max(0.0, float(cfg.decrease_pct)),
            ),
            initial_risk=base,
            current_risk=base,
        )

    @property
    def max_risk_cap(self) -> float:
        return self.initial_risk * (self.config.max_risk_pct / 100.0)

    def lots_for_entry(
        self,
        entry_premium: float,
        stop_loss_pct: float,
        contract_value: float,
    ) -> int:
        budget = self.initial_risk if not self.config.enabled else self.current_risk
        return lots_from_max_risk(budget, entry_premium, stop_loss_pct, contract_value)

    def on_closed(self, pnl: float) -> None:
        if not self.config.enabled:
            return
        step_up = self.initial_risk * (self.config.increase_pct / 100.0)
        step_down = self.initial_risk * (self.config.decrease_pct / 100.0)
        if pnl > 0:
            self.win_streak += 1
            self.loss_streak = 0
            after = self.config.after_profits
            if after > 0 and self.win_streak % after == 0:
                self.current_risk = max(self.initial_risk, self.current_risk - step_down)
        elif pnl < 0:
            self.loss_streak += 1
            self.win_streak = 0
            after = self.config.after_losses
            if after > 0 and self.loss_streak % after == 0:
                self.current_risk = min(self.max_risk_cap, self.current_risk + step_up)
        else:
            self.win_streak = 0
            self.loss_streak = 0


@dataclass
class BacktestResult:
    trades: list[ClosedTrade] = field(default_factory=list)
    summary: BacktestSummary = field(default_factory=BacktestSummary)
    settings: dict[str, Any] = field(default_factory=dict)


def _trade_row_date(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST).strftime("%Y-%m-%d %H:%M")


def _streak_stats(outcomes: list[str]) -> tuple[int, int, int, int]:
    """Return (max_win_len, max_win_count, max_loss_len, max_loss_count).

    outcomes items are ``\"win\"``, ``\"loss\"``, or ``\"flat\"`` (flat breaks both streaks).
    """
    win_lens: list[int] = []
    loss_lens: list[int] = []
    cur = 0
    kind: str | None = None

    def flush() -> None:
        nonlocal cur, kind
        if kind == "win" and cur > 0:
            win_lens.append(cur)
        elif kind == "loss" and cur > 0:
            loss_lens.append(cur)
        cur = 0
        kind = None

    for outcome in outcomes:
        if outcome == "win":
            if kind == "win":
                cur += 1
            else:
                flush()
                kind = "win"
                cur = 1
        elif outcome == "loss":
            if kind == "loss":
                cur += 1
            else:
                flush()
                kind = "loss"
                cur = 1
        else:
            flush()
    flush()

    max_win_len = max(win_lens) if win_lens else 0
    max_loss_len = max(loss_lens) if loss_lens else 0
    max_win_count = sum(1 for n in win_lens if n == max_win_len) if max_win_len else 0
    max_loss_count = sum(1 for n in loss_lens if n == max_loss_len) if max_loss_len else 0
    return max_win_len, max_win_count, max_loss_len, max_loss_count


def compute_summary(trades: list[ClosedTrade]) -> BacktestSummary:
    summary = BacktestSummary(total_trades=len(trades))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    dd_peak_time: str | None = None
    current_dd_from: str | None = None
    max_dd_from: str | None = None
    max_dd_to: str | None = None
    outcomes: list[str] = []
    win_pnls: list[float] = []
    loss_pnls: list[float] = []

    for trade in trades:
        summary.total_pnl += trade.pnl
        if trade.direction == "LONG":
            summary.long_trades += 1
            summary.long_pnl += trade.pnl
        else:
            summary.short_trades += 1
            summary.short_pnl += trade.pnl

        if summary.max_profit is None or trade.pnl > summary.max_profit:
            summary.max_profit = trade.pnl
            summary.max_profit_date = trade.date
        if summary.max_loss is None or trade.pnl < summary.max_loss:
            summary.max_loss = trade.pnl
            summary.max_loss_date = trade.date

        if trade.pnl > 0:
            summary.win_count += 1
            win_pnls.append(trade.pnl)
            outcomes.append("win")
        elif trade.pnl < 0:
            summary.loss_count += 1
            loss_pnls.append(trade.pnl)
            outcomes.append("loss")
        else:
            outcomes.append("flat")

        equity += trade.pnl
        exit_label = trade.date
        if equity >= peak:
            peak = equity
            dd_peak_time = exit_label
            current_dd_from = None
        else:
            dd = peak - equity
            if current_dd_from is None:
                current_dd_from = dd_peak_time or exit_label
            if dd > max_dd:
                max_dd = dd
                max_dd_from = current_dd_from
                max_dd_to = exit_label

    summary.max_drawdown = max_dd
    summary.max_dd_from = max_dd_from
    summary.max_dd_to = max_dd_to
    (
        summary.max_win_streak_len,
        summary.max_win_streak_count,
        summary.max_loss_streak_len,
        summary.max_loss_streak_count,
    ) = _streak_stats(outcomes)
    summary.avg_profit = (sum(win_pnls) / len(win_pnls)) if win_pnls else None
    summary.avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else None
    return summary


def run_backtest(
    bars: list[OhlcBar],
    *,
    underlying: str,
    quantity: float = DEFAULT_QUANTITY,
    max_risk: float = 100.0,
    st_period: int = DEFAULT_ST_PERIOD,
    st_multiplier: float = DEFAULT_ST_MULTIPLIER,
    ema_length: int = DEFAULT_EMA_LENGTH,
    min_premium_pct: float = DEFAULT_MIN_PREMIUM_PCT,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT,
    breakeven_decay_pct: float = DEFAULT_BREAKEVEN_DECAY_PCT,
    window_start: int | None = None,
    premium_lookup: PremiumLookup,
    option_candle_lookup: OptionCandleLookup,
    dynamic_sizing: DynamicSizingConfig | None = None,
) -> BacktestResult:
    inds = compute_indicator_bars(
        bars,
        st_period=st_period,
        st_multiplier=st_multiplier,
        ema_length=ema_length,
    )
    sizing = DynamicSizingState.create(float(max_risk), dynamic_sizing)
    cv = contract_value_for(underlying)

    open_long: OpenTrade | None = None
    open_short: OpenTrade | None = None
    closed: list[ClosedTrade] = []

    # After TP, allow same-bar / later re-entry while criteria hold.
    reenter_long = False
    reenter_short = False

    def _close_and_size(
        trade: OpenTrade, exit_time: int, exit_price: float, reason: ExitReason
    ) -> ClosedTrade:
        row = _close_trade(trade, exit_time, exit_price, reason)
        sizing.on_closed(row.pnl)
        return row

    for bar in inds:
        if window_start is not None and bar.time < window_start:
            continue
        if bar.ema is None or bar.st.st_line is None:
            continue

        before_len = len(closed)
        # --- manage open positions ---
        open_long, reenter_long = _manage_open(
            open_long,
            bar,
            closed,
            option_candle_lookup=option_candle_lookup,
            reenter_flag=reenter_long,
            take_profit_pct=take_profit_pct,
        )
        open_short, reenter_short = _manage_open(
            open_short,
            bar,
            closed,
            option_candle_lookup=option_candle_lookup,
            reenter_flag=reenter_short,
            take_profit_pct=take_profit_pct,
        )
        for newly in closed[before_len:]:
            sizing.on_closed(newly.pnl)

        # --- entries ---
        if open_long is None and (entry_ready(bar, "LONG") or reenter_long):
            if entry_ready(bar, "LONG"):
                opened = _try_open(
                    bar,
                    "LONG",
                    underlying,
                    sizing,
                    cv,
                    min_premium_pct,
                    premium_lookup,
                    stop_loss_pct=stop_loss_pct,
                    breakeven_decay_pct=breakeven_decay_pct,
                )
                if opened:
                    open_long = opened
                    reenter_long = False
        if open_short is None and (entry_ready(bar, "SHORT") or reenter_short):
            if entry_ready(bar, "SHORT"):
                opened = _try_open(
                    bar,
                    "SHORT",
                    underlying,
                    sizing,
                    cv,
                    min_premium_pct,
                    premium_lookup,
                    stop_loss_pct=stop_loss_pct,
                    breakeven_decay_pct=breakeven_decay_pct,
                )
                if opened:
                    open_short = opened
                    reenter_short = False

    # Flatten remaining at end of data
    if inds:
        last = inds[-1]
        for side_trade in (open_long, open_short):
            if side_trade is None:
                continue
            high, low, close = option_candle_lookup(side_trade.option_symbol, last.time)
            exit_px = close if close is not None else side_trade.premium_received
            closed.append(
                _close_and_size(side_trade, last.time, float(exit_px), "end_of_data")
            )

    settings = {
        "underlying": underlying,
        "quantity": quantity,
        "maxRisk": sizing.initial_risk,
        "stPeriod": st_period,
        "stMultiplier": st_multiplier,
        "emaLength": ema_length,
        "minPremiumPct": min_premium_pct,
        "stopLossPct": stop_loss_pct,
        "takeProfitPct": take_profit_pct,
        "breakevenDecayPct": breakeven_decay_pct,
        "dynamicSizingEnabled": sizing.config.enabled,
        "dynAfterLosses": sizing.config.after_losses,
        "dynIncreasePct": sizing.config.increase_pct,
        "dynMaxRiskPct": sizing.config.max_risk_pct,
        "dynAfterProfits": sizing.config.after_profits,
        "dynDecreasePct": sizing.config.decrease_pct,
    }
    return BacktestResult(trades=closed, summary=compute_summary(closed), settings=settings)


def _try_open(
    bar: IndicatorBar,
    direction: Direction,
    underlying: str,
    sizing: DynamicSizingState,
    cv: float,
    min_premium_pct: float,
    premium_lookup: PremiumLookup,
    *,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    breakeven_decay_pct: float = DEFAULT_BREAKEVEN_DECAY_PCT,
) -> OpenTrade | None:
    signal = build_entry_signal(bar, direction)
    if signal is None:
        return None
    close_ts = bar_close_unix(bar.time)
    resolved = resolve_option_waterfall(
        underlying=underlying,
        direction=direction,
        perp_price=bar.close,
        bar_close_unix=close_ts,
        min_premium_pct=min_premium_pct,
        premium_lookup=premium_lookup,
    )
    if resolved is None:
        return None
    prem = float(resolved.premium)
    trade_cv = resolved.contract_value or cv
    lots = sizing.lots_for_entry(prem, stop_loss_pct, trade_cv)
    return OpenTrade(
        direction=direction,
        entry_time=bar.time,
        st_colour=signal.st_colour,
        st_colour_change_time=signal.st_colour_change_time,
        ema_price=signal.ema,
        strike=resolved.strike,
        expiry=resolved.expiry.isoformat(),
        option_symbol=resolved.symbol,
        premium_received=prem,
        contract_value=trade_cv,
        lots=lots,
        stop_loss_pct=float(stop_loss_pct),
        breakeven_decay_pct=float(breakeven_decay_pct),
    )


def _manage_open(
    trade: OpenTrade | None,
    bar: IndicatorBar,
    closed: list[ClosedTrade],
    *,
    option_candle_lookup: OptionCandleLookup,
    reenter_flag: bool,
    take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT,
    stop_loss_pct: float | None = None,
) -> tuple[OpenTrade | None, bool]:
    if trade is None:
        return None, reenter_flag

    # Decay hedge: open opposite leg when main has melted enough.
    if (
        trade.pair_id
        and trade.hedge_pending
        and trade.hedge_symbol
        and trade.hedge_premium_received is None
    ):
        _h, _l, main_close = option_candle_lookup(trade.option_symbol, bar.time)
        if main_close is not None and should_open_decay_hedge(
            trade.premium_received, float(main_close), trade.pair_hedge_decay_pct
        ):
            _hh, _hl, hedge_close = option_candle_lookup(trade.hedge_symbol, bar.time)
            if hedge_close is not None and float(hedge_close) > 0:
                trade.hedge_premium_received = float(hedge_close)
                trade.hedge_entry_time = bar.time
                trade.hedge_pending = False

    high, low, close = option_candle_lookup(trade.option_symbol, bar.time)
    # Prefer trade-local stop (may move to BE); fall back to caller's stop_loss_pct for older callers.
    effective_sl_pct = float(trade.stop_loss_pct if stop_loss_pct is None else stop_loss_pct)
    probe = low if low is not None else close
    if (
        probe is not None
        and should_move_sl_to_breakeven(
            trade.premium_received,
            float(probe),
            decay_pct=trade.breakeven_decay_pct,
            already_moved=trade.sl_moved_to_breakeven,
        )
    ):
        trade.stop_loss_pct = 0.0
        trade.sl_moved_to_breakeven = True
        effective_sl_pct = 0.0

    hedge_live = trade.hedge_symbol is not None and trade.hedge_premium_received is not None
    immediate_pair = trade.pair_hedge_mode == "immediate" and hedge_live
    # Immediate pair: favor exit is premium parity only (disable solo TP).
    effective_tp = 100.0 if immediate_pair else take_profit_pct

    reason, exit_px = evaluate_premium_brackets(
        entry_premium=trade.premium_received,
        option_high=high,
        option_low=low,
        option_close=close,
        stop_loss_pct=effective_sl_pct,
        take_profit_pct=effective_tp,
        stop_premium_level=trade.premium_received if trade.sl_moved_to_breakeven else None,
    )

    if reason is None and immediate_pair and trade.hedge_symbol:
        _hh, _hl, hedge_close = option_candle_lookup(trade.hedge_symbol, bar.time)
        main_px = close if close is not None else trade.premium_received
        hedge_px = hedge_close if hedge_close is not None else trade.hedge_premium_received
        if main_px is not None and hedge_px is not None:
            main_side = str(trade.main_option_side or "").upper()
            put_px = float(main_px) if main_side == "PUT" else float(hedge_px)
            call_px = float(main_px) if main_side == "CALL" else float(hedge_px)
            if pair_premiums_equal(put_px, call_px):
                reason = "pair_parity"
                exit_px = float(main_px)

    if reason is None and opposite_st_exit(trade.direction, bar):
        reason = "st_flip"
        exit_px = close if close is not None else trade.premium_received

    if reason is None:
        expiry_day = None
        try:
            expiry_day = date.fromisoformat(str(trade.expiry)[:10])
        except ValueError:
            expiry_day = parse_option_symbol_expiry(trade.option_symbol)
        if expiry_day is not None:
            cutoff = force_close_cutoff_unix(expiry_day)
            bar_close = bar_close_unix(bar.time)
            # Last 1H bar that closes at or before 17:15 IST on expiry day.
            if bar_close <= cutoff < bar_close + 3600:
                reason = "expiry_close"
                exit_px = close if close is not None else trade.premium_received

    if reason is None:
        return trade, False

    main_reason: ExitReason = reason  # type: ignore[assignment]
    hedge_reason: ExitReason = "pair_parity" if reason == "pair_parity" else "pair_stop"

    closed.append(
        _close_trade(trade, bar.time, float(exit_px or trade.premium_received), main_reason)
    )
    if hedge_live and trade.hedge_symbol and trade.hedge_premium_received is not None:
        _hh, _hl, hedge_close = option_candle_lookup(trade.hedge_symbol, bar.time)
        hedge_exit = float(hedge_close) if hedge_close is not None else float(trade.hedge_premium_received)
        closed.append(_close_hedge_leg(trade, bar.time, hedge_exit, hedge_reason))

    # No TP re-entry for immediate pair (parity owns favor exit).
    allow_reenter = reason in {"take_profit", "expiry_close"} and not immediate_pair
    return None, allow_reenter


def _close_trade(trade: OpenTrade, exit_time: int, exit_price: float, reason: ExitReason) -> ClosedTrade:
    pnl = short_option_pnl(trade.premium_received, exit_price, trade.contract_value, trade.lots)
    return ClosedTrade(
        date=_trade_row_date(trade.entry_time),
        direction=trade.direction,
        st_colour=trade.st_colour,
        st_colour_change_time=format_ist(trade.st_colour_change_time),
        ema_price=trade.ema_price,
        strike=trade.strike,
        expiry_date=trade.expiry,
        premium_received=trade.premium_received,
        exit_price=exit_price,
        exit_reason=reason,
        pnl=pnl,
        entry_time=trade.entry_time,
        exit_time=exit_time,
        option_symbol=trade.option_symbol,
        lots=int(trade.lots),
        pair_id=trade.pair_id,
        leg_role="main" if trade.pair_id else None,
    )


def _close_hedge_leg(
    trade: OpenTrade,
    exit_time: int,
    exit_price: float,
    reason: ExitReason,
) -> ClosedTrade:
    entry = float(trade.hedge_premium_received or 0)
    entry_time = int(trade.hedge_entry_time or trade.entry_time)
    pnl = short_option_pnl(entry, exit_price, trade.contract_value, trade.lots)
    return ClosedTrade(
        date=_trade_row_date(entry_time),
        direction=trade.direction,
        st_colour=trade.st_colour,
        st_colour_change_time=format_ist(trade.st_colour_change_time),
        ema_price=trade.ema_price,
        strike=trade.strike,
        expiry_date=trade.expiry,
        premium_received=entry,
        exit_price=exit_price,
        exit_reason=reason,
        pnl=pnl,
        entry_time=entry_time,
        exit_time=exit_time,
        option_symbol=str(trade.hedge_symbol or ""),
        lots=int(trade.lots),
        pair_id=trade.pair_id,
        leg_role="hedge",
    )


def result_to_dict(result: BacktestResult) -> dict[str, Any]:
    return {
        "settings": result.settings,
        "summary": asdict(result.summary),
        "trades": [asdict(t) for t in result.trades],
    }

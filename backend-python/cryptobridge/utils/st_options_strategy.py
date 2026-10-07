"""Shared strategy constants and pure signal / exit helpers for 1H ST Options."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cryptobridge.utils.st_options_indicators import IndicatorBar
from cryptobridge.utils.st_options_resolver import Direction

STOP_PREMIUM_MULT = 2.05  # entry + 105% of entry → stop at 2.05× premium
TARGET_PREMIUM_MULT = 0.05  # 95% melted → 5% remaining
DEFAULT_STOP_LOSS_PCT = 105.0  # premium rise above entry that stops out a short option
DEFAULT_TAKE_PROFIT_PCT = 95.0  # premium melt from entry that books profit
DEFAULT_BREAKEVEN_DECAY_PCT = 40.0  # move SL to entry after this % premium melt; 0 = off
DEFAULT_ST_PERIOD = 10
DEFAULT_ST_MULTIPLIER = 3.0
DEFAULT_EMA_LENGTH = 10
DEFAULT_MIN_PREMIUM_PCT = 5.0
DEFAULT_QUANTITY = 1.0
DEFAULT_MAX_ST_DISTANCE_PCT = 0.3  # backtest: max |close−ST|/close×100; 0 = off
WARMUP_DAYS = 120
RESOLUTION = "1h"
RESOLUTION_SECONDS = 3600

ExitReason = Literal[
    "st_flip",
    "stop_loss",
    "take_profit",
    "end_of_data",
    "expiry_close",
    "expired",
    "force_closed",
    "pair_parity",
    "pair_stop",
]


@dataclass(frozen=True)
class EntrySignal:
    direction: Direction
    bar_time: int
    close: float
    ema: float
    st_line: float
    st_colour: str
    st_colour_change_time: int | None


def sentiment_from_bar(bar: IndicatorBar) -> Direction | None:
    if bar.st.st_line is None or bar.st.direction is None or bar.ema is None:
        return None
    if bar.close > bar.st.st_line:
        return "LONG"
    if bar.close < bar.st.st_line:
        return "SHORT"
    return None


def long_entry_ready(bar: IndicatorBar) -> bool:
    if bar.ema is None or bar.st.st_line is None:
        return False
    return bar.close < bar.ema and bar.close > bar.st.st_line


def short_entry_ready(bar: IndicatorBar) -> bool:
    if bar.ema is None or bar.st.st_line is None:
        return False
    return bar.close > bar.ema and bar.close < bar.st.st_line


def entry_ready(bar: IndicatorBar, direction: Direction) -> bool:
    return long_entry_ready(bar) if direction == "LONG" else short_entry_ready(bar)


def close_st_distance_pct(bar: IndicatorBar) -> float | None:
    """|close − ST line| as a percent of close. None if ST/close unavailable."""
    if bar.st.st_line is None:
        return None
    close = float(bar.close)
    if close <= 0:
        return None
    return abs(close - float(bar.st.st_line)) / close * 100.0


def st_distance_within(bar: IndicatorBar, max_pct: float) -> bool:
    """True when max_pct <= 0 (off) or known distance is strictly below max_pct."""
    if float(max_pct) <= 0:
        return True
    dist = close_st_distance_pct(bar)
    if dist is None:
        return False
    return dist < float(max_pct)


def build_entry_signal(bar: IndicatorBar, direction: Direction) -> EntrySignal | None:
    if not entry_ready(bar, direction):
        return None
    assert bar.ema is not None and bar.st.st_line is not None and bar.st_colour is not None
    return EntrySignal(
        direction=direction,
        bar_time=bar.time,
        close=bar.close,
        ema=bar.ema,
        st_line=bar.st.st_line,
        st_colour=bar.st_colour,
        st_colour_change_time=bar.st_colour_change_time,
    )


def opposite_st_exit(direction: Direction, bar: IndicatorBar) -> bool:
    """Exit when perp closes on the opposite side of ST."""
    if bar.st.st_line is None:
        return False
    if direction == "LONG":
        return bar.close < bar.st.st_line
    return bar.close > bar.st.st_line


def stop_premium(entry_premium: float, stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT) -> float:
    """SL level: entry + stop_loss_pct% of entry (default 105% → 2.05× entry)."""
    entry = float(entry_premium)
    return entry + entry * (float(stop_loss_pct) / 100.0)


def target_premium(entry_premium: float, take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT) -> float:
    """TP level: take_profit_pct% melted (default 95% → 5% of entry remaining)."""
    remaining = max(0.0, (100.0 - float(take_profit_pct)) / 100.0)
    return float(entry_premium) * remaining


def premium_decay_pct(entry_premium: float, live_premium: float) -> float:
    """How far premium has melted from entry (0 = unchanged, 100 = worthless)."""
    entry = float(entry_premium)
    if entry <= 0:
        return 0.0
    live = float(live_premium)
    return max(0.0, (entry - live) / entry * 100.0)


def breakeven_trigger_premium(entry_premium: float, decay_pct: float) -> float:
    """Premium level at which decay_pct% has melted (entry * (1 - decay/100))."""
    return float(entry_premium) * max(0.0, (100.0 - float(decay_pct)) / 100.0)


def should_move_sl_to_breakeven(
    entry_premium: float,
    live_premium: float,
    *,
    decay_pct: float,
    already_moved: bool,
) -> bool:
    """True when decay trail is enabled, not yet moved, and live premium hit the decay threshold."""
    if already_moved:
        return False
    pct = float(decay_pct)
    if pct <= 0 or pct >= 100:
        return False
    entry = float(entry_premium)
    live = float(live_premium)
    if entry <= 0:
        return False
    return live <= breakeven_trigger_premium(entry, pct)


def evaluate_premium_brackets(
    *,
    entry_premium: float,
    option_high: float | None,
    option_low: float | None,
    option_close: float | None,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT,
    stop_premium_level: float | None = None,
) -> tuple[ExitReason | None, float | None]:
    """
    Prefer intrabar high/low so SL/TP are not missed.
    SL checked before TP if both touched in the same bar (conservative for short options).
    When stop_premium_level is set (e.g. after move-to-BE), use it instead of stop_loss_pct.
    """
    stop = (
        float(stop_premium_level)
        if stop_premium_level is not None
        else stop_premium(entry_premium, stop_loss_pct)
    )
    target = target_premium(entry_premium, take_profit_pct)
    high = option_high if option_high is not None else option_close
    low = option_low if option_low is not None else option_close
    if high is None or low is None:
        return None, None
    if high >= stop:
        return "stop_loss", stop
    # take_profit_pct >= 100 disables TP (used for immediate pair hedge).
    if float(take_profit_pct) < 100.0 and low <= target:
        return "take_profit", target
    return None, None


def short_option_pnl(entry_premium: float, exit_premium: float, contract_value: float, lots: int) -> float:
    return (float(entry_premium) - float(exit_premium)) * float(contract_value) * int(lots)

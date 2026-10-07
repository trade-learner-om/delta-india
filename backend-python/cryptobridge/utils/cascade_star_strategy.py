"""Cascade Star signal math. No I/O.

Short: four consecutive downside bars, then an upside-rejection candle.
Long is the mirror and stays behind ``direction``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence
from zoneinfo import ZoneInfo

from cryptobridge.utils.choppiness import choppiness
from cryptobridge.utils.st_options_indicators import OhlcBar

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_SESSION_START = time(15, 30)
DEFAULT_SESSION_END = time(23, 0)
DEFAULT_CHOP_LENGTH = 14
DEFAULT_CHOP_MAX = 61.8
DEFAULT_TARGET_R = 3.3
SETUP_BARS = 4
UPSIDE_REJECTION_RATIO = 0.60
STAR_WICK_BODY_RATIO = 2.0
STAR_WICK_RANGE_RATIO = 0.50
STAR_OPPOSITE_WICK_RATIO = 0.30
RESOLUTION_SECONDS = 300


@dataclass(frozen=True)
class TradeLevels:
    entry: float
    stop: float
    target: float
    r: float
    tick: float


@dataclass(frozen=True)
class SignalDecision:
    take: bool
    reason: str
    chop: float | None = None
    levels: TradeLevels | None = None


def candle_range(bar: OhlcBar) -> float:
    return float(bar.high) - float(bar.low)


def upper_wick(bar: OhlcBar) -> float:
    return float(bar.high) - max(float(bar.open), float(bar.close))


def lower_wick(bar: OhlcBar) -> float:
    return min(float(bar.open), float(bar.close)) - float(bar.low)


def candle_body(bar: OhlcBar) -> float:
    return abs(float(bar.close) - float(bar.open))


def is_red(bar: OhlcBar) -> bool:
    return float(bar.close) < float(bar.open)


def is_green(bar: OhlcBar) -> bool:
    return float(bar.close) > float(bar.open)


def _star_shape(dominant: float, opposite: float, body: float, span: float) -> bool:
    if body <= 0 or span <= 0 or dominant <= 0:
        return False
    return (
        dominant >= STAR_WICK_BODY_RATIO * body
        and dominant / span >= STAR_WICK_RANGE_RATIO
        and opposite < STAR_OPPOSITE_WICK_RATIO * dominant
    )


def is_shooting_star(bar: OhlcBar) -> bool:
    span = candle_range(bar)
    return _star_shape(upper_wick(bar), lower_wick(bar), candle_body(bar), span)


def is_hammer(bar: OhlcBar) -> bool:
    span = candle_range(bar)
    return _star_shape(lower_wick(bar), upper_wick(bar), candle_body(bar), span)


def is_upside_rejection(bar: OhlcBar) -> bool:
    span = candle_range(bar)
    if span <= 0:
        return False
    if upper_wick(bar) / span >= UPSIDE_REJECTION_RATIO:
        return True
    return is_shooting_star(bar)


def is_downside_rejection(bar: OhlcBar) -> bool:
    span = candle_range(bar)
    if span <= 0:
        return False
    if lower_wick(bar) / span >= UPSIDE_REJECTION_RATIO:
        return True
    return is_hammer(bar)


def setup_bar_qualifies(bar: OhlcBar, direction: str) -> bool:
    side = _direction(direction)
    if side == "SHORT":
        return is_red(bar) or is_upside_rejection(bar)
    return is_green(bar) or is_downside_rejection(bar)


def signal_bar_qualifies(bar: OhlcBar, direction: str) -> bool:
    side = _direction(direction)
    if side == "SHORT":
        return is_upside_rejection(bar)
    return is_downside_rejection(bar)


def _prior_bars_qualify(bars: Sequence[OhlcBar], index: int, count: int, direction: str) -> bool:
    if index < count:
        return False
    return all(setup_bar_qualifies(bars[index - offset], direction) for offset in range(1, count + 1))


def pattern_ready(bars: Sequence[OhlcBar], index: int, direction: str) -> bool:
    """Signal when this bar is a rejection and the cascade is already in place.

    The rejection may be the 4th candle (three qualifying bars before it) or the
    candle after four qualifying bars, when that 4th candle was not itself a rejection.
    """
    if index < 0 or index >= len(bars):
        return False
    if not signal_bar_qualifies(bars[index], direction):
        return False
    if _prior_bars_qualify(bars, index, SETUP_BARS - 1, direction):
        return True
    return _prior_bars_qualify(bars, index, SETUP_BARS, direction)


def point_size(tick_size: float | None) -> float:
    if tick_size is not None and float(tick_size) > 0:
        return float(tick_size)
    return 0.01


def round_to_tick(price: float, tick: float) -> float:
    quant = Decimal(str(tick))
    steps = (Decimal(str(price)) / quant).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    rounded = steps * quant
    exponent = quant.normalize().as_tuple().exponent
    decimals = max(0, -exponent) if isinstance(exponent, int) else 0
    return round(float(rounded), decimals)


def trade_levels(bar: OhlcBar, direction: str, tick_size: float | None, target_r: float = DEFAULT_TARGET_R) -> TradeLevels:
    tick = point_size(tick_size)
    if float(target_r) <= 0:
        raise ValueError("target_r must be > 0")
    side = _direction(direction)
    if side == "SHORT":
        entry = round_to_tick(float(bar.low) - tick, tick)
        stop = round_to_tick(float(bar.high) + tick, tick)
        risk = stop - entry
        target = round_to_tick(entry - float(target_r) * risk, tick)
    else:
        entry = round_to_tick(float(bar.high) + tick, tick)
        stop = round_to_tick(float(bar.low) - tick, tick)
        risk = entry - stop
        target = round_to_tick(entry + float(target_r) * risk, tick)
    return TradeLevels(entry=entry, stop=stop, target=target, r=risk, tick=tick)


def candle_close_in_session(
    open_unix: int,
    *,
    resolution_seconds: int = RESOLUTION_SECONDS,
    session_start: time = DEFAULT_SESSION_START,
    session_end: time = DEFAULT_SESSION_END,
) -> bool:
    """True when the candle's close timestamp falls inside the IST window, bounds included."""
    close_at = datetime.fromtimestamp(int(open_unix) + int(resolution_seconds), tz=timezone.utc).astimezone(IST)
    clock = close_at.time().replace(microsecond=0)
    return session_start <= clock <= session_end


def clock_outside_session(
    now: datetime,
    *,
    session_start: time = DEFAULT_SESSION_START,
    session_end: time = DEFAULT_SESSION_END,
) -> bool:
    local = now.astimezone(IST).time().replace(microsecond=0)
    return local < session_start or local >= session_end


def closed_bars(bars: Sequence[OhlcBar], now_unix: int, resolution_seconds: int = RESOLUTION_SECONDS) -> list[OhlcBar]:
    return [bar for bar in bars if int(bar.time) + resolution_seconds <= int(now_unix)]


def bars_after_signal(bars: Sequence[OhlcBar], signal_bar_time: int) -> int:
    return sum(1 for bar in bars if int(bar.time) > int(signal_bar_time))


def pending_cancel_reason(
    *,
    signal_bar_time: int,
    bars: Sequence[OhlcBar],
    now: datetime,
    fill_timeout_bars: int = 5,
    session_start: time = DEFAULT_SESSION_START,
    session_end: time = DEFAULT_SESSION_END,
) -> str | None:
    if bars_after_signal(bars, signal_bar_time) >= int(fill_timeout_bars):
        return "entry_timeout"
    if clock_outside_session(now, session_start=session_start, session_end=session_end):
        return "session_end"
    return None


def evaluate_signal(
    bars: Sequence[OhlcBar],
    index: int,
    *,
    direction: str,
    tick_size: float | None,
    chop_length: int = DEFAULT_CHOP_LENGTH,
    chop_max: float = DEFAULT_CHOP_MAX,
    target_r: float = DEFAULT_TARGET_R,
    session_start: time = DEFAULT_SESSION_START,
    session_end: time = DEFAULT_SESSION_END,
    resolution_seconds: int = RESOLUTION_SECONDS,
) -> SignalDecision:
    if index < 0 or index >= len(bars):
        return SignalDecision(False, "pattern")
    bar = bars[index]
    if not candle_close_in_session(
        bar.time,
        resolution_seconds=resolution_seconds,
        session_start=session_start,
        session_end=session_end,
    ):
        return SignalDecision(False, "session")
    if not pattern_ready(bars, index, direction):
        return SignalDecision(False, "pattern")
    if index + 1 < int(chop_length):
        return SignalDecision(False, "warmup")
    series = choppiness(
        [item.high for item in bars],
        [item.low for item in bars],
        [item.close for item in bars],
        int(chop_length),
    )
    value = series[index]
    if value is None or float(value) >= float(chop_max):
        return SignalDecision(False, "chop", chop=value)
    levels = trade_levels(bar, direction, tick_size, target_r)
    return SignalDecision(True, "ok", chop=value, levels=levels)


def parse_hhmm(value: str, fallback: time) -> time:
    text = str(value or "").strip()
    try:
        hour, minute = text.split(":", 1)
        parsed = time(int(hour), int(minute))
    except (TypeError, ValueError):
        return fallback
    return parsed


def _direction(direction: str) -> str:
    side = str(direction or "").strip().upper()
    if side not in {"SHORT", "LONG"}:
        raise ValueError("direction must be SHORT or LONG")
    return side


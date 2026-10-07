"""TradingView-parity EMA + SuperTrend for 1H ST Options.

SuperTrend matches Pine `ta.supertrend`: HL2 source, RMA ATR (`ta.atr`),
ternary band pinning vs prior final bands, and Pine direction state machine.
EMA matches `ta.ema` with SMA seed over the first `length` bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class OhlcBar:
    time: int  # unix seconds (bar open)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class SuperTrendPoint:
    time: int
    hl2: float
    atr: float | None
    upper_band: float | None
    lower_band: float | None
    st_line: float | None
    direction: int | None  # 1 = green/up, -1 = red/down
    flipped: bool


@dataclass(frozen=True)
class IndicatorBar:
    time: int
    open: float
    high: float
    low: float
    close: float
    ema: float | None
    st: SuperTrendPoint
    st_colour: str | None  # "green" | "red"
    st_colour_change_time: int | None  # unix of last ST flip (inclusive)


def true_range(high: float, low: float, prev_close: float | None) -> float:
    if prev_close is None:
        return high - low
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def rma(values: Sequence[float | None], length: int) -> list[float | None]:
    """Wilder RMA / TradingView `ta.rma`."""
    if length < 1:
        raise ValueError("length must be >= 1")
    out: list[float | None] = [None] * len(values)
    alpha = 1.0 / length
    prev: float | None = None
    seed_sum = 0.0
    seed_count = 0
    for i, raw in enumerate(values):
        if raw is None:
            out[i] = None
            continue
        value = float(raw)
        if prev is None:
            seed_sum += value
            seed_count += 1
            if seed_count < length:
                out[i] = None
                continue
            prev = seed_sum / length
            out[i] = prev
            continue
        prev = alpha * value + (1.0 - alpha) * prev
        out[i] = prev
    return out


def ema_sma_seed(closes: Sequence[float], length: int) -> list[float | None]:
    """TradingView `ta.ema` — SMA of first `length` closes, then EMA."""
    if length < 1:
        raise ValueError("length must be >= 1")
    out: list[float | None] = [None] * len(closes)
    if len(closes) < length:
        return out
    alpha = 2.0 / (length + 1)
    seed = sum(closes[:length]) / length
    out[length - 1] = seed
    prev = seed
    for i in range(length, len(closes)):
        prev = alpha * closes[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def calculate_supertrend(
    bars: Sequence[OhlcBar],
    period: int = 10,
    multiplier: float = 3.0,
) -> list[SuperTrendPoint]:
    """Pine `ta.supertrend` default parity (HL2 + RMA ATR)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    if multiplier <= 0:
        raise ValueError("multiplier must be > 0")

    trs: list[float | None] = []
    hl2s: list[float] = []
    for i, bar in enumerate(bars):
        prev_close = bars[i - 1].close if i > 0 else None
        trs.append(true_range(bar.high, bar.low, prev_close))
        hl2s.append((bar.high + bar.low) / 2.0)

    atrs = rma(trs, period)
    points: list[SuperTrendPoint] = []
    prev_upper: float | None = None
    prev_lower: float | None = None
    prev_dir: int | None = None

    for i, bar in enumerate(bars):
        atr = atrs[i]
        hl2 = hl2s[i]
        if atr is None:
            points.append(
                SuperTrendPoint(
                    time=bar.time,
                    hl2=hl2,
                    atr=None,
                    upper_band=None,
                    lower_band=None,
                    st_line=None,
                    direction=None,
                    flipped=False,
                )
            )
            continue

        basic_upper = hl2 + multiplier * atr
        basic_lower = hl2 - multiplier * atr

        if prev_upper is None or prev_lower is None:
            # First ATR bar: initialize red on upper band (TV / prior SPS parity).
            upper = basic_upper
            lower = basic_lower
            direction = -1
            line = upper
            flipped = False
        else:
            prior_close = bars[i - 1].close
            # Ternary pinning vs prior final bands.
            if prior_close > prev_upper:
                upper = basic_upper
            else:
                upper = min(basic_upper, prev_upper)
            if prior_close < prev_lower:
                lower = basic_lower
            else:
                lower = max(basic_lower, prev_lower)

            # Pine direction state machine using current pinned bands.
            assert prev_dir is not None
            if prev_dir == -1:  # was on upper (red)
                direction = 1 if bar.close > upper else -1
            else:  # was on lower (green)
                direction = -1 if bar.close < lower else 1

            line = lower if direction == 1 else upper
            flipped = direction != prev_dir

        points.append(
            SuperTrendPoint(
                time=bar.time,
                hl2=hl2,
                atr=atr,
                upper_band=upper,
                lower_band=lower,
                st_line=line,
                direction=direction,
                flipped=flipped,
            )
        )
        prev_upper = upper
        prev_lower = lower
        prev_dir = direction

    return points


def compute_indicator_bars(
    bars: Sequence[OhlcBar],
    *,
    st_period: int = 10,
    st_multiplier: float = 3.0,
    ema_length: int = 10,
) -> list[IndicatorBar]:
    closes = [b.close for b in bars]
    emas = ema_sma_seed(closes, ema_length)
    sts = calculate_supertrend(bars, period=st_period, multiplier=st_multiplier)

    out: list[IndicatorBar] = []
    last_flip_time: int | None = None
    for bar, ema, st in zip(bars, emas, sts):
        colour = None
        if st.direction == 1:
            colour = "green"
        elif st.direction == -1:
            colour = "red"
        if st.flipped and st.direction is not None:
            last_flip_time = bar.time
        out.append(
            IndicatorBar(
                time=bar.time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                ema=ema,
                st=st,
                st_colour=colour,
                st_colour_change_time=last_flip_time,
            )
        )
    return out


# Alias matching historical SPS naming.
compute_supertrend_tv = calculate_supertrend

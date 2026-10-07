"""TradingView Choppiness Index (Pine built-in CHOP).

Matches the study formula:

    100 * log10(sum(ta.atr(1), length) / (ta.highest(high, length) - ta.lowest(low, length))) / log10(length)

``ta.atr(1)`` is Wilder RMA of true range with length 1, which equals true range.
``ta.highest`` / ``ta.lowest`` use the last ``length`` bars, including the current bar.
A zero high-low span is undefined and returned as None (treated as choppy by the strategy).
"""

from __future__ import annotations

import math
from typing import Sequence

from cryptobridge.utils.st_options_indicators import rma, true_range


def atr_length_one(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float | None]:
    """TradingView ``ta.atr(1)``."""
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("high, low, and close series must be the same length")
    true_ranges: list[float] = []
    prev_close: float | None = None
    for high, low, close in zip(highs, lows, closes):
        true_ranges.append(true_range(float(high), float(low), prev_close))
        prev_close = float(close)
    return rma(true_ranges, 1)


def choppiness(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    length: int = 14,
) -> list[float | None]:
    """Choppiness Index aligned to each bar. None until ``length`` ATR(1) values exist or when the span is 0."""
    if length < 2:
        raise ValueError("length must be >= 2")
    atr = atr_length_one(highs, lows, closes)
    out: list[float | None] = [None] * len(atr)
    log_length = math.log10(length)
    for index in range(length - 1, len(atr)):
        window = atr[index - length + 1 : index + 1]
        if any(value is None for value in window):
            continue
        highest = max(float(highs[i]) for i in range(index - length + 1, index + 1))
        lowest = min(float(lows[i]) for i in range(index - length + 1, index + 1))
        span = highest - lowest
        if span <= 0:
            continue
        total = sum(float(value) for value in window if value is not None)
        if total <= 0:
            out[index] = 0.0
            continue
        out[index] = 100.0 * math.log10(total / span) / log_length
    return out

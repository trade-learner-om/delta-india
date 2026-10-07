from datetime import datetime, time, timezone

from cryptobridge.utils.cascade_star_strategy import (
    IST,
    bars_after_signal,
    candle_close_in_session,
    evaluate_signal,
    is_upside_rejection,
    pending_cancel_reason,
    round_to_tick,
    setup_bar_qualifies,
    trade_levels,
)
from cryptobridge.utils.choppiness import choppiness
from cryptobridge.utils.st_options_indicators import OhlcBar


def _bar(open_time: int, open_: float, high: float, low: float, close: float) -> OhlcBar:
    return OhlcBar(time=open_time, open=open_, high=high, low=low, close=close)


def _ist_open(year: int, month: int, day: int, hour: int, minute: int) -> int:
    close_at = datetime(year, month, day, hour, minute, tzinfo=IST)
    return int(close_at.timestamp()) - 300


def _red(open_time: int, open_: float, close: float) -> OhlcBar:
    return _bar(open_time, open_, open_, close, close)


def _star(open_time: int, open_: float = 110.0, close: float = 100.0, high: float = 140.0, low: float = 99.0) -> OhlcBar:
    return _bar(open_time, open_, high, low, close)


def test_sixty_percent_rejection_and_shooting_star():
    rejection = _bar(0, 100, 130, 90, 102)  # upper 28 / range 40 = 0.70
    assert is_upside_rejection(rejection)
    exact = _bar(0, 100, 160, 100, 124)  # upper 36 / range 60 = 0.60
    assert is_upside_rejection(exact)
    below = _bar(0, 100, 150, 100, 130)  # upper 20 / range 50 = 0.40, body too large for a star
    assert not is_upside_rejection(below)
    # Body 10, upper wick 21, lower wick 5: a shooting star whose upper wick is 58% of the range.
    star = _bar(0, 100, 131, 95, 110)
    assert upper_ratio(star) < 0.60
    assert is_upside_rejection(star)
    assert not is_upside_rejection(_bar(0, 100, 100, 100, 100))


def upper_ratio(bar: OhlcBar) -> float:
    return (bar.high - max(bar.open, bar.close)) / (bar.high - bar.low)


def test_colour_exception_counts_a_green_rejection_in_the_four():
    start = _ist_open(2026, 10, 4, 16, 0)
    times = [start + i * 300 for i in range(5)]
    green_star = _star(times[1], open_=100, close=108, high=140, low=99)
    assert green_star.close > green_star.open
    assert setup_bar_qualifies(green_star, "SHORT")
    bars = [
        _red(times[0], 120, 110),
        green_star,
        _red(times[2], 112, 104),
        _red(times[3], 104, 96),
        _star(times[4]),
    ]
    # Widen the chop gate so this test is about colour, not the index.
    decision = evaluate_signal(bars, 4, direction="SHORT", tick_size=0.5, chop_length=2, chop_max=101)
    assert decision.take
    assert decision.reason == "ok"


def test_plain_green_candle_breaks_the_run():
    start = _ist_open(2026, 10, 4, 16, 0)
    times = [start + i * 300 for i in range(5)]
    bars = [
        _red(times[0], 120, 110),
        _bar(times[1], 110, 118, 109, 117),
        _red(times[2], 117, 108),
        _red(times[3], 108, 100),
        _star(times[4]),
    ]
    decision = evaluate_signal(bars, 4, direction="SHORT", tick_size=0.5, chop_length=2, chop_max=101)
    assert not decision.take
    assert decision.reason == "pattern"


def test_short_levels_are_one_tick_beyond_the_star_and_target_3_3_r():
    bar = _star(0, open_=110, close=100, high=110, low=100)
    levels = trade_levels(bar, "SHORT", 0.5, 3.3)
    assert levels.entry == 99.5
    assert levels.stop == 110.5
    risk = 11.0
    assert levels.r == risk
    assert levels.target == round_to_tick(99.5 - 3.3 * risk, 0.5)
    assert levels.target == 63.0


def test_long_mirror_levels():
    bar = _bar(0, 100, 110, 90, 108)
    levels = trade_levels(bar, "LONG", 1.0, 3.3)
    assert levels.entry == 111.0
    assert levels.stop == 89.0
    assert levels.r == 22.0
    assert levels.target == round_to_tick(111.0 + 3.3 * 22.0, 1.0)


def test_session_window_includes_1530_and_2300_ist():
    assert candle_close_in_session(_ist_open(2026, 10, 4, 15, 30))
    assert candle_close_in_session(_ist_open(2026, 10, 4, 23, 0))
    assert not candle_close_in_session(_ist_open(2026, 10, 4, 15, 25))
    assert not candle_close_in_session(_ist_open(2026, 10, 4, 23, 5))


def test_signal_inside_session_can_use_setup_bars_from_before_1530():
    signal_open = _ist_open(2026, 10, 4, 15, 30)
    times = [signal_open - (4 - i) * 300 for i in range(5)]
    assert not candle_close_in_session(times[0])
    bars = [
        _red(times[0], 130, 120),
        _red(times[1], 120, 112),
        _red(times[2], 112, 104),
        _red(times[3], 104, 96),
        _star(times[4], open_=96, close=90, high=120, low=88),
    ]
    decision = evaluate_signal(bars, 4, direction="SHORT", tick_size=0.5, chop_length=2, chop_max=101)
    assert decision.take


def test_chop_at_tradingview_upper_band_skips_the_entry():
    start = _ist_open(2026, 10, 4, 16, 0)
    bars = []
    for i in range(14):
        open_time = start + i * 300
        # Constant range keeps CHOP at 100, which is the sideways reading.
        bars.append(_bar(open_time, 100, 110, 90, 100))
    # Force the last five candles into a valid short pattern without leaving the same high/low span.
    for offset, (open_, close) in enumerate(((108, 100), (104, 96), (100, 92), (96, 88))):
        index = 9 + offset
        bars[index] = _red(bars[index].time, open_, close)
        bars[index] = _bar(bars[index].time, open_, 110, 90, close)
    bars[13] = _bar(bars[13].time, 100, 110, 90, 92)
    # upper wick 10 / range 20 = 0.50 is not 60%. Build a real star inside the same 90-110 span.
    bars[13] = _bar(bars[13].time, 96, 110, 90, 94)
    values = choppiness([bar.high for bar in bars], [bar.low for bar in bars], [bar.close for bar in bars], 14)
    assert values[13] is not None and values[13] >= 61.8
    decision = evaluate_signal(bars, 13, direction="SHORT", tick_size=0.5, chop_length=14, chop_max=61.8)
    assert not decision.take
    assert decision.reason == "chop"


def test_trending_cascade_is_taken_when_chop_is_below_the_band():
    start = _ist_open(2026, 10, 4, 18, 0)
    bars = []
    price = 1000.0
    for i in range(20):
        open_ = price
        close = open_ - 1.0
        bars.append(_bar(start + i * 300, open_, open_, close, close))
        price = close - 4.0
    bars[-1] = _bar(bars[-1].time, bars[-2].close, bars[-2].close + 30.0, bars[-2].close - 2.0, bars[-2].close - 1.0)
    decision = evaluate_signal(bars, len(bars) - 1, direction="SHORT", tick_size=0.5, chop_max=61.8)
    assert decision.chop is not None and decision.chop < 61.8
    assert decision.take
    assert decision.levels is not None
    assert decision.levels.entry == round_to_tick(bars[-1].low - 0.5, 0.5)
    blocked = evaluate_signal(bars, len(bars) - 1, direction="SHORT", tick_size=0.5, chop_max=decision.chop)
    assert not blocked.take
    assert blocked.reason == "chop"


def test_pending_entry_cancels_after_five_bars_or_at_session_end():
    signal = _ist_open(2026, 10, 4, 22, 30)
    later = [_bar(signal + (i + 1) * 300, 1, 2, 0, 1) for i in range(5)]
    assert bars_after_signal(later[:4], signal) == 4
    assert pending_cancel_reason(
        signal_bar_time=signal,
        bars=later[:4],
        now=datetime(2026, 10, 4, 22, 50, tzinfo=IST),
    ) is None
    assert pending_cancel_reason(
        signal_bar_time=signal,
        bars=later,
        now=datetime(2026, 10, 4, 22, 55, tzinfo=IST),
    ) == "entry_timeout"
    assert pending_cancel_reason(
        signal_bar_time=signal,
        bars=later[:1],
        now=datetime(2026, 10, 4, 23, 0, tzinfo=IST),
    ) == "session_end"


def test_fourth_candle_rejection_is_the_signal():
    start = _ist_open(2026, 10, 4, 16, 0)
    times = [start + i * 300 for i in range(4)]
    bars = [
        _red(times[0], 120, 110),
        _red(times[1], 110, 102),
        _red(times[2], 102, 96),
        _star(times[3], open_=96, close=90, high=120, low=88),
    ]
    decision = evaluate_signal(bars, 3, direction="SHORT", tick_size=0.5, chop_length=2, chop_max=101)
    assert decision.take
    assert decision.levels is not None
    assert decision.levels.entry == round_to_tick(88 - 0.5, 0.5)


def test_four_plain_reds_do_not_signal():
    start = _ist_open(2026, 10, 4, 16, 0)
    times = [start + i * 300 for i in range(4)]
    bars = [
        _red(times[0], 120, 110),
        _red(times[1], 110, 102),
        _red(times[2], 102, 96),
        _red(times[3], 96, 90),
    ]
    decision = evaluate_signal(bars, 3, direction="SHORT", tick_size=0.5, chop_length=2, chop_max=101)
    assert not decision.take
    assert decision.reason == "pattern"


def test_session_clock_uses_ist_not_utc():
    # 15:30 IST is 10:00 UTC. A UTC reading of 15:30 would be outside the session.
    open_time = int(datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc).timestamp()) - 300
    assert candle_close_in_session(open_time)
    assert candle_close_in_session(open_time, session_start=time(15, 30), session_end=time(23, 0))

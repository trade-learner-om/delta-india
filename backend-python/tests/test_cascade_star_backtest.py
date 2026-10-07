from datetime import datetime

from cryptobridge.utils.cascade_star_backtest import GST_RATE, DEFAULT_TAKER_RATE, simulate
from cryptobridge.utils.cascade_star_strategy import IST
from cryptobridge.utils.st_options_indicators import OhlcBar


def _bar(open_time: int, open_: float, high: float, low: float, close: float) -> OhlcBar:
    return OhlcBar(time=open_time, open=open_, high=high, low=low, close=close)


def _ist_open(hour: int, minute: int) -> int:
    close_at = datetime(2026, 10, 4, hour, minute, tzinfo=IST)
    return int(close_at.timestamp()) - 300


def _red(open_time: int, open_: float, close: float) -> OhlcBar:
    return _bar(open_time, open_, open_, close, close)


def _cascade(start_open: int) -> list[OhlcBar]:
    times = [start_open + i * 300 for i in range(4)]
    return [
        _red(times[0], 110, 106),
        _red(times[1], 106, 104),
        _red(times[2], 104, 102),
        _bar(times[3], 101, 104, 100, 100.5),
    ]


def test_fourth_candle_fills_then_reaches_target():
    bars = _cascade(_ist_open(16, 0))
    signal = bars[-1].time
    bars.append(_bar(signal + 300, 101, 102, 99, 100))
    bars.append(_bar(signal + 600, 90, 92, 82, 85))
    result = simulate(bars, tick_size=0.5, sizing_mode="lots", lots=1, chop_length=2, chop_max=101, contract_value=0.001)
    filled = [trade for trade in result["trades"] if trade["fillPrice"] is not None]
    assert len(filled) == 1
    trade = filled[0]
    assert trade["signalTime"] == signal
    assert trade["exitReason"] == "target"
    assert trade["fillPrice"] == 99.5
    assert trade["exitPrice"] == 83.0
    gross = (99.5 - 83.0) * 0.001
    fee = DEFAULT_TAKER_RATE * (0.001 * 99.5 + 0.001 * 83.0) * (1 + GST_RATE)
    assert abs(trade["grossPnl"] - gross) < 1e-12
    assert abs(trade["fee"] - fee) < 1e-12
    assert abs(trade["pnl"] - (gross - fee)) < 1e-12
    assert result["summary"]["trades"] == 1
    assert result["summary"]["wins"] == 1


def test_stop_wins_when_the_fill_bar_also_reaches_the_target():
    bars = _cascade(_ist_open(16, 0))
    signal = bars[-1].time
    bars.append(_bar(signal + 300, 100, 110, 80, 90))
    result = simulate(bars, tick_size=0.5, sizing_mode="lots", lots=1, chop_length=2, chop_max=101)
    trade = result["trades"][0]
    assert trade["exitReason"] == "sl"
    assert trade["exitPrice"] == 104.5
    assert trade["fillPrice"] == 99.5


def test_unfilled_stop_cancels_after_five_bars():
    bars = _cascade(_ist_open(18, 0))
    signal = bars[-1].time
    for step in range(1, 6):
        bars.append(_bar(signal + step * 300, 110, 112, 108, 109))
    result = simulate(bars, tick_size=0.5, sizing_mode="lots", lots=1, chop_length=2, chop_max=101)
    assert result["summary"]["trades"] == 0
    assert result["summary"]["cancelled"] == 1
    assert result["trades"][0]["exitReason"] == "entry_timeout"


def test_choppy_market_takes_no_trade():
    start = _ist_open(16, 0)
    bars = [_bar(start + i * 300, 100, 110, 90, 100) for i in range(14)]
    for offset, (open_, close) in enumerate(((108, 100), (104, 96), (100, 92), (96, 88))):
        index = 9 + offset
        bars[index] = _bar(bars[index].time, open_, 110, 90, close)
    bars[13] = _bar(bars[13].time, 96, 110, 90, 94)
    result = simulate(bars, tick_size=0.5, sizing_mode="lots", lots=1, chop_length=14, chop_max=61.8)
    assert result["trades"] == []
    assert result["summary"]["trades"] == 0

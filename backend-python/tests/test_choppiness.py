import math

from cryptobridge.utils.choppiness import atr_length_one, choppiness


def test_atr_length_one_equals_true_range():
    highs = [10.0, 12.0, 11.0]
    lows = [8.0, 9.0, 10.0]
    closes = [9.0, 11.0, 10.5]
    atr = atr_length_one(highs, lows, closes)
    assert atr[0] == 2.0
    assert atr[1] == 3.0  # max(3, |12-9|, |9-9|)
    assert atr[2] == 1.0  # max(1, |11-11|, |10-11|)


def test_choppiness_matches_tradingview_on_constant_range():
    # Every bar has range 20 and closes where the previous bar closed, so ATR(1) is 20.
    # sum(ATR(1), 14) / (highest - lowest) = 280 / 20 = 14, and CHOP = 100.
    highs = [110.0] * 14
    lows = [90.0] * 14
    closes = [100.0] * 14
    values = choppiness(highs, lows, closes, 14)
    assert values[12] is None
    assert values[13] is not None
    assert abs(values[13] - 100.0) < 1e-9
    expected = 100.0 * math.log10(14.0) / math.log10(14.0)
    assert abs(values[13] - expected) < 1e-9


def test_choppiness_zero_span_is_none():
    highs = [100.0] * 14
    lows = [100.0] * 14
    closes = [100.0] * 14
    values = choppiness(highs, lows, closes, 14)
    assert values[13] is None

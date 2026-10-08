from cryptobridge.mt5.client import day_change_percent


def test_day_change_percent_from_daily_open():
    assert day_change_percent(4125.42, 4100) == (4125.42 - 4100) / 4100 * 100


def test_day_change_percent_skips_a_missing_or_zero_open():
    assert day_change_percent(100, None) is None
    assert day_change_percent(None, 100) is None
    assert day_change_percent(100, 0) is None

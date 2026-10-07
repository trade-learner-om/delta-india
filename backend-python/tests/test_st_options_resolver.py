from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from cryptobridge.utils.st_options_resolver import (
    ResolvedOption,
    collect_option_waterfall,
    delta_option_symbol,
    eligible_expiries,
    expiry_dates_t0_t1,
    fixed_mode_expiry,
    option_side_for_direction,
    parse_option_symbol_expiry,
    parse_strike_type,
    pick_above_average_volume,
    premium_meets_min,
    product_matches_expiry,
    resolve_backtest_strike,
    resolve_fixed_moneyness,
    resolve_option_waterfall,
    resolve_supertrend_atm,
    snap_atm,
    strike_band_min_max,
    strike_from_moneyness,
    strike_ladder,
)
from cryptobridge.utils.st_options_strategy import (
    STOP_PREMIUM_MULT,
    close_st_distance_pct,
    evaluate_premium_brackets,
    long_entry_ready,
    short_entry_ready,
    short_option_pnl,
    st_distance_within,
    stop_premium,
)
from cryptobridge.utils.st_options_indicators import IndicatorBar, SuperTrendPoint


def test_atm_and_strike_ladder():
    assert snap_atm(3005, 20) == 3000
    assert snap_atm(3015, 20) == 3020
    put_ladder = strike_ladder(3000, "PUT", "ETH", otm_depth=3, itm_depth=3)
    assert put_ladder[0] == (3, 2940.0)  # OTM3
    assert put_ladder[3] == (0, 3000.0)  # ATM
    assert put_ladder[-1] == (-3, 3060.0)  # ITM3
    call_ladder = strike_ladder(3000, "CALL", "ETH", otm_depth=3, itm_depth=3)
    assert call_ladder[0] == (3, 3060.0)  # OTM3
    assert call_ladder[3] == (0, 3000.0)
    assert call_ladder[-1] == (-3, 2940.0)


def test_strike_ladder_live_atm_plus_minus_one():
    ladder = strike_ladder(3000, "PUT", "ETH", otm_depth=1, itm_depth=1)
    assert [m for m, _ in ladder] == [1, 0, -1]
    assert [s for _, s in ladder] == [2980.0, 3000.0, 3020.0]


def test_option_side_and_symbol():
    assert option_side_for_direction("LONG") == "PUT"
    assert option_side_for_direction("SHORT") == "CALL"
    assert delta_option_symbol("PUT", "BTC", 90000, date(2026, 7, 24)) == "P-BTC-90000-240726"


def test_parse_option_symbol_expiry_and_match():
    assert parse_option_symbol_expiry("C-BTC-65000-310724") == date(2024, 7, 31)
    assert parse_option_symbol_expiry("C-BTC-65000-240726") == date(2026, 7, 24)
    assert parse_option_symbol_expiry("bad") is None
    matching = SimpleNamespace(symbol="C-BTC-65000-240726", expiry=None)
    mismatch = SimpleNamespace(symbol="C-BTC-65000-310724", expiry=None)
    assert product_matches_expiry(matching, date(2026, 7, 24))
    assert not product_matches_expiry(mismatch, date(2026, 7, 24))


def test_t0_t1_ist():
    ts = int(datetime(2026, 7, 24, 6, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    pairs = expiry_dates_t0_t1(ts)
    assert pairs[0] == (0, date(2026, 7, 24))
    assert pairs[1] == (1, date(2026, 7, 25))


def test_eligible_expiries_t0_before_and_after_cutoff():
    early = int(datetime(2026, 7, 24, 9, 30, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    late = int(datetime(2026, 7, 24, 11, 30, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    early_pairs = eligible_expiries(early)
    late_pairs = eligible_expiries(late)
    assert early_pairs[0] == (0, date(2026, 7, 24))
    assert early_pairs[1] == (1, date(2026, 7, 25))
    assert late_pairs == [(1, date(2026, 7, 25))]


def test_waterfall_prefers_furthest_otm():
    ts = int(datetime(2026, 7, 24, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    # ATM and OTM2 both clear floor; furthest OTM (OTM2) should win.
    premiums = {
        ("P-ETH-3000-240726", 3000): 200.0,  # ATM
        ("P-ETH-2960-240726", 2960): 160.0,  # OTM2 — further OTM
    }

    def lookup(symbol, expiry, strike, side):
        return premiums.get((symbol, strike))

    resolved = resolve_option_waterfall(
        underlying="ETH",
        direction="LONG",
        perp_price=3000,
        bar_close_unix=ts,
        min_premium_pct=5.0,
        premium_lookup=lookup,
    )
    assert resolved is not None
    assert resolved.strike == 2960
    assert resolved.moneyness_steps == 2
    assert resolved.expiry_offset == 0


def test_waterfall_tie_goes_to_t1():
    ts = int(datetime(2026, 7, 24, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    premiums = {
        ("P-ETH-2960-240726", date(2026, 7, 24), 2960): 160.0,
        ("P-ETH-2960-250726", date(2026, 7, 25), 2960): 155.0,
    }

    def lookup(symbol, expiry, strike, side):
        return premiums.get((symbol, expiry, strike))

    resolved = resolve_option_waterfall(
        underlying="ETH",
        direction="LONG",
        perp_price=3000,
        bar_close_unix=ts,
        min_premium_pct=5.0,
        premium_lookup=lookup,
    )
    assert resolved is not None
    assert resolved.strike == 2960
    assert resolved.expiry_offset == 1
    assert resolved.expiry == date(2026, 7, 25)


def test_waterfall_excludes_t0_after_cutoff():
    ts = int(datetime(2026, 7, 24, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    premiums = {
        ("P-ETH-3000-240726", date(2026, 7, 24), 3000): 200.0,
        ("P-ETH-3000-250726", date(2026, 7, 25), 3000): 180.0,
    }

    def lookup(symbol, expiry, strike, side):
        return premiums.get((symbol, expiry, strike))

    resolved = resolve_option_waterfall(
        underlying="ETH",
        direction="LONG",
        perp_price=3000,
        bar_close_unix=ts,
        min_premium_pct=5.0,
        premium_lookup=lookup,
    )
    assert resolved is not None
    assert resolved.expiry_offset == 1
    assert resolved.expiry == date(2026, 7, 25)


def test_waterfall_returns_none_when_all_premiums_below_gate():
    ts = int(datetime(2026, 7, 24, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())

    def lookup(symbol, expiry, strike, side):
        return 50.0  # always below 5% of 3000 (=150)

    resolved = resolve_option_waterfall(
        underlying="ETH",
        direction="LONG",
        perp_price=3000,
        bar_close_unix=ts,
        min_premium_pct=5.0,
        premium_lookup=lookup,
    )
    assert resolved is None
    assert premium_meets_min(50.0, 3000, 5.0) is False


def test_collect_waterfall_depth_one_stays_in_atm_band():
    ts = int(datetime(2026, 7, 24, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())

    def lookup(symbol, expiry, strike, side):
        return 200.0

    candidates = collect_option_waterfall(
        underlying="ETH",
        direction="LONG",
        perp_price=3000,
        bar_close_unix=ts,
        min_premium_pct=5.0,
        premium_lookup=lookup,
        depth=1,
    )
    assert candidates
    assert all(abs(c.moneyness_steps) <= 1 for c in candidates)


def _vol_opt(symbol: str, steps: int = 0) -> ResolvedOption:
    return ResolvedOption(
        underlying="BTC",
        direction="LONG",
        option_side="PUT",
        strike=63000,
        expiry=date(2026, 8, 17),
        expiry_offset=0,
        itm_steps=max(0, -steps),
        symbol=symbol,
        premium=500,
        perp_price=63000,
        min_premium=100,
        moneyness_steps=steps,
    )


def test_pick_above_average_volume_keeps_above_skips_below():
    high = _vol_opt("P-BTC-63200-170826", 1)
    mid = _vol_opt("P-BTC-63000-170826", 0)
    low = _vol_opt("P-BTC-62800-170826", -1)
    kept = pick_above_average_volume(
        [high, mid, low],
        {high.symbol: 100, mid.symbol: 10, low.symbol: 10},
    )
    assert [c.symbol for c in kept] == [high.symbol]


def test_pick_above_average_volume_skips_when_all_zero_or_missing():
    a = _vol_opt("P-BTC-63200-170826", 1)
    b = _vol_opt("P-BTC-63000-170826", 0)
    assert pick_above_average_volume([a, b], {a.symbol: 0, b.symbol: 0}) == []
    assert pick_above_average_volume([a, b], {}) == []


def test_stop_premium_is_entry_plus_105_pct():
    assert STOP_PREMIUM_MULT == 2.05
    assert stop_premium(100) == 205.0


def test_premium_brackets_sl_before_tp():
    reason, px = evaluate_premium_brackets(
        entry_premium=100,
        option_high=210,
        option_low=4,
        option_close=50,
    )
    assert reason == "stop_loss"
    assert px == 205.0


def test_strike_band_covers_window_minmax_not_median():
    closes = [62000.0, 63500.0, 65000.0]
    band = strike_band_min_max(closes, "BTC", depth=3)
    assert 61400.0 in band
    assert 65600.0 in band
    assert min(band) <= 61400.0
    assert max(band) >= 65600.0


def test_premium_brackets_tp():
    reason, px = evaluate_premium_brackets(
        entry_premium=100,
        option_high=90,
        option_low=4,
        option_close=10,
    )
    assert reason == "take_profit"
    assert px == 5.0


def test_premium_brackets_custom_stop_loss_pct():
    # 50% rise → stop at 150 for entry 100
    reason, px = evaluate_premium_brackets(
        entry_premium=100,
        option_high=160,
        option_low=90,
        option_close=140,
        stop_loss_pct=50,
        take_profit_pct=95,
    )
    assert reason == "stop_loss"
    assert px == 150.0


def test_premium_brackets_custom_take_profit_pct():
    # 60% melt → target at 40 for entry 100
    reason, px = evaluate_premium_brackets(
        entry_premium=100,
        option_high=110,
        option_low=35,
        option_close=45,
        stop_loss_pct=105,
        take_profit_pct=60,
    )
    assert reason == "take_profit"
    assert px == 40.0


def test_should_move_sl_to_breakeven_at_decay():
    from cryptobridge.utils.st_options_strategy import should_move_sl_to_breakeven

    assert should_move_sl_to_breakeven(100, 60, decay_pct=40, already_moved=False) is True
    assert should_move_sl_to_breakeven(100, 61, decay_pct=40, already_moved=False) is False
    assert should_move_sl_to_breakeven(100, 50, decay_pct=40, already_moved=True) is False
    assert should_move_sl_to_breakeven(100, 50, decay_pct=0, already_moved=False) is False


def test_evaluate_brackets_uses_stored_stop_premium_level():
    # After BE move, stop is entry (100); high 100.5 trips stop at 100
    reason, px = evaluate_premium_brackets(
        entry_premium=100,
        option_high=100.5,
        option_low=90,
        option_close=95,
        stop_loss_pct=105,
        take_profit_pct=95,
        stop_premium_level=100,
    )
    assert reason == "stop_loss"
    assert px == 100.0


def test_fixed_mode_expiry_before_and_after_0530():
    before = int(datetime(2026, 7, 24, 5, 29, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    at = int(datetime(2026, 7, 24, 5, 30, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    after = int(datetime(2026, 7, 24, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    assert fixed_mode_expiry(before) == (0, date(2026, 7, 24))
    assert fixed_mode_expiry(at) == (1, date(2026, 7, 25))
    assert fixed_mode_expiry(after) == (1, date(2026, 7, 25))


def test_parse_strike_type_and_moneyness():
    assert parse_strike_type("ATM") == 0
    assert parse_strike_type("OTM3") == 3
    assert parse_strike_type("ITM2") == -2
    assert strike_from_moneyness(3000, "PUT", "ETH", 2) == 2960.0
    assert strike_from_moneyness(3000, "CALL", "ETH", 2) == 3040.0


def test_resolve_fixed_moneyness_same_day_before_cutoff():
    ts = int(datetime(2026, 7, 24, 4, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    premiums = {("P-ETH-2960-240726", date(2026, 7, 24), 2960.0): 120.0}

    def lookup(symbol, expiry, strike, side):
        return premiums.get((symbol, expiry, float(strike)))

    resolved = resolve_fixed_moneyness(
        underlying="ETH",
        direction="LONG",
        perp_price=3000,
        bar_close_unix=ts,
        strike_type="OTM2",
        premium_lookup=lookup,
    )
    assert resolved is not None
    assert resolved.strike == 2960
    assert resolved.expiry_offset == 0
    assert resolved.expiry == date(2026, 7, 24)


def test_resolve_fixed_skips_when_premium_missing_no_fallback():
    ts = int(datetime(2026, 7, 24, 4, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    # Only T+1 has premium — fixed mode must not fall back.
    premiums = {("P-ETH-3000-250726", date(2026, 7, 25), 3000.0): 120.0}

    def lookup(symbol, expiry, strike, side):
        return premiums.get((symbol, expiry, float(strike)))

    assert (
        resolve_fixed_moneyness(
            underlying="ETH",
            direction="LONG",
            perp_price=3000,
            bar_close_unix=ts,
            strike_type="ATM",
            premium_lookup=lookup,
        )
        is None
    )


def test_resolve_supertrend_atm_and_min_abs_dispatch():
    ts = int(datetime(2026, 7, 24, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    premiums = {
        ("P-ETH-2980-240726", date(2026, 7, 24), 2980.0): 80.0,
        ("P-ETH-2940-240726", date(2026, 7, 24), 2940.0): 55.0,
    }

    def lookup(symbol, expiry, strike, side):
        return premiums.get((symbol, expiry, float(strike)))

    st = resolve_supertrend_atm(
        underlying="ETH",
        direction="LONG",
        st_line=2975,
        perp_price=3000,
        bar_close_unix=ts,
        premium_lookup=lookup,
    )
    assert st is not None
    assert st.strike == 2980.0

    abs_hit = resolve_backtest_strike(
        mode="min_abs",
        underlying="ETH",
        direction="LONG",
        perp_price=3000,
        bar_close_unix=ts,
        premium_lookup=lookup,
        min_premium_abs=50,
    )
    assert abs_hit is not None
    assert abs_hit.strike == 2940.0  # furthest OTM clearing abs floor


def test_short_option_pnl():
    assert short_option_pnl(100, 40, 0.01, 100) == 60.0


def test_entry_ready_helpers():
    st = SuperTrendPoint(
        time=1,
        hl2=100,
        atr=1,
        upper_band=105,
        lower_band=95,
        st_line=95,
        direction=1,
        flipped=False,
    )
    bar = IndicatorBar(
        time=1,
        open=100,
        high=101,
        low=99,
        close=98,
        ema=100,
        st=st,
        st_colour="green",
        st_colour_change_time=1,
    )
    assert long_entry_ready(bar)
    assert not short_entry_ready(bar)


def test_close_st_distance_pct_and_within():
    st = SuperTrendPoint(
        time=1,
        hl2=100,
        atr=1,
        upper_band=105,
        lower_band=95,
        st_line=99.8,
        direction=1,
        flipped=False,
    )
    bar = IndicatorBar(
        time=1,
        open=100,
        high=101,
        low=99,
        close=100.0,
        ema=101,
        st=st,
        st_colour="green",
        st_colour_change_time=1,
    )
    # |100 - 99.8| / 100 * 100 = 0.2%
    assert close_st_distance_pct(bar) == pytest.approx(0.2)
    assert st_distance_within(bar, 0.3) is True
    assert st_distance_within(bar, 0.2) is False  # must be strictly < max
    assert st_distance_within(bar, 0) is True  # off

    far = IndicatorBar(
        time=1,
        open=100,
        high=101,
        low=99,
        close=100.0,
        ema=101,
        st=SuperTrendPoint(
            time=1,
            hl2=100,
            atr=1,
            upper_band=105,
            lower_band=95,
            st_line=99.0,
            direction=1,
            flipped=False,
        ),
        st_colour="green",
        st_colour_change_time=1,
    )
    # 1.0% > 0.3
    assert close_st_distance_pct(far) == pytest.approx(1.0)
    assert st_distance_within(far, 0.3) is False

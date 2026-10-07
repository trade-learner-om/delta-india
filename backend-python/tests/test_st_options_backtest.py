from datetime import datetime
from zoneinfo import ZoneInfo

from cryptobridge.utils.st_options_backtest import (
    ClosedTrade,
    DynamicSizingConfig,
    DynamicSizingState,
    OpenTrade,
    _manage_open,
    arm_skip_after_take_profit,
    clear_formation_block,
    compute_summary,
    consume_skip_setup,
    entry_limit_price,
    formation_blocks_entry,
    lots_from_max_risk,
    lots_from_max_risk_or_none,
    LIVE_SL_SLIPPAGE_BUFFER_PCT,
)
from cryptobridge.utils.st_options_indicators import IndicatorBar, SuperTrendPoint


def _trade(pnl, *, direction="LONG", entry_time=1, symbol="P-ETH-100-010126"):
    return ClosedTrade(
        date="2026-01-01 10:00",
        direction=direction,
        st_colour="green",
        st_colour_change_time=None,
        ema_price=100,
        strike=100,
        expiry_date="2026-01-01",
        premium_received=10,
        exit_price=5,
        exit_reason="take_profit",
        pnl=pnl,
        entry_time=entry_time,
        exit_time=entry_time + 1,
        option_symbol=symbol,
        lots=1,
    )


def test_compute_summary_counts_and_drawdown():
    trades = [
        _trade(50, direction="LONG", entry_time=1),
        _trade(-40, direction="SHORT", entry_time=3, symbol="C-ETH-100-020126"),
    ]
    summary = compute_summary(trades)
    assert summary.total_trades == 2
    assert summary.long_trades == 1
    assert summary.short_trades == 1
    assert summary.total_pnl == 10
    assert summary.long_pnl == 50
    assert summary.short_pnl == -40
    assert summary.max_profit == 50
    assert summary.max_loss == -40
    assert summary.max_drawdown == 40
    assert summary.win_count == 1
    assert summary.loss_count == 1
    assert summary.avg_profit == 50
    assert summary.avg_loss == -40


def test_compute_summary_max_streak_as_len_and_count():
    # Wins: streaks of 2, then 4, then 4 → max len 4 occurred twice
    # Losses: streaks of 1, then 3, then 3 → max len 3 occurred twice
    pnls = [1, 1, -1, 1, 1, 1, 1, -1, -1, -1, 1, 1, 1, 1, -1, -1, -1]
    trades = [_trade(p, entry_time=i + 1) for i, p in enumerate(pnls)]
    summary = compute_summary(trades)
    assert summary.max_win_streak_len == 4
    assert summary.max_win_streak_count == 2
    assert summary.max_loss_streak_len == 3
    assert summary.max_loss_streak_count == 2


def test_compute_summary_zero_pnl_breaks_streaks():
    trades = [_trade(1), _trade(0), _trade(1), _trade(1)]
    summary = compute_summary(trades)
    assert summary.max_win_streak_len == 2
    assert summary.max_win_streak_count == 1
    assert summary.win_count == 3


def test_lots_from_max_risk():
    # ETH cv=0.01; premium 100; SL 30% → risk/lot = 100*0.3*0.01 = 0.3
    # maxRisk 30 → floor(30/0.3) = 100 lots
    assert lots_from_max_risk(30, 100, 30, 0.01) == 100
    assert lots_from_max_risk(0.2, 100, 30, 0.01) == 1  # floor below 1 → 1
    assert lots_from_max_risk(100, 100, 105, 0.001) == max(
        1, int(100 / (100 * 1.05 * 0.001))
    )


def test_lots_from_max_risk_user_example_btc_15pct():
    # entry 500, SL 15%, BTC cv 0.001, maxRisk 15 → 200 lots
    assert lots_from_max_risk(15, 500, 15, 0.001) == 200
    assert lots_from_max_risk_or_none(15, 500, 15, 0.001) == 200


def test_lots_from_max_risk_or_none_skips_when_one_lot_exceeds():
    # ETH: prem 2000, SL 105%, cv 0.01 → risk/lot = 21 > maxRisk 15
    assert lots_from_max_risk_or_none(15, 2000, 105, 0.01) is None
    assert lots_from_max_risk(15, 2000, 105, 0.01) == 1  # old helper still forces 1


def test_lots_from_max_risk_live_slippage_buffer():
    # Observed PUT: fill 540.80, 15% SL, BTC cv, $15 maxRisk → 184 lots at theoretical stop.
    assert lots_from_max_risk_or_none(15, 540.80, 15, 0.001) == 184
    # Live sizes as if SL% were 15×1.4=21% so a 654 stop-market fill stays near -$15.
    buffered = lots_from_max_risk_or_none(
        15, 540.80, 15, 0.001, slippage_buffer_pct=LIVE_SL_SLIPPAGE_BUFFER_PCT
    )
    assert LIVE_SL_SLIPPAGE_BUFFER_PCT == 40.0
    assert buffered == 132
    realized = (540.80 - 654.10) * 0.001 * buffered
    assert realized >= -15.05


def test_entry_limit_price_minus_one():
    assert entry_limit_price(500) == 499.0
    assert entry_limit_price(1) is None  # 1 - 1 = 0 invalid
    assert entry_limit_price(0.5) is None
    assert entry_limit_price(0) is None


def test_dynamic_sizing_increases_risk_budget_by_pct_of_base():
    sizing = DynamicSizingState.create(
        100,
        DynamicSizingConfig(
            enabled=True,
            after_losses=2,
            increase_pct=10,
            max_risk_pct=200,
            after_profits=2,
            decrease_pct=10,
        ),
    )
    # premium 100, SL 30%, cv 0.01 → risk/lot=0.3 → lots = floor(budget/0.3)
    assert sizing.lots_for_entry(100, 30, 0.01) == 333  # floor(100/0.3)
    sizing.on_closed(-1)
    assert sizing.current_risk == 100
    sizing.on_closed(-1)
    assert sizing.current_risk == 110  # +10% of base
    assert sizing.lots_for_entry(100, 30, 0.01) == 366  # floor(110/0.3)
    sizing.on_closed(-1)
    sizing.on_closed(-1)
    assert sizing.current_risk == 120
    sizing.on_closed(1)
    sizing.on_closed(1)
    assert sizing.current_risk == 110
    sizing.on_closed(1)
    sizing.on_closed(1)
    assert sizing.current_risk == 100  # floor at base
    # Cap at 200%
    for _ in range(30):
        sizing.on_closed(-1)
        sizing.on_closed(-1)
    assert sizing.current_risk == 200


def test_manage_open_force_closes_on_expiry_cutoff_bar():
    """Last 1H bar with close <= 17:15 IST on expiry day exits with expiry_close."""
    open_ts = int(datetime(2026, 7, 24, 15, 30, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    st = SuperTrendPoint(
        time=open_ts,
        hl2=3000,
        atr=1,
        upper_band=3010,
        lower_band=2990,
        st_line=2990,
        direction=1,
        flipped=False,
    )
    bar = IndicatorBar(
        time=open_ts,
        open=3000,
        high=3010,
        low=2990,
        close=3005,
        ema=3010,
        st=st,
        st_colour="green",
        st_colour_change_time=open_ts,
    )
    trade = OpenTrade(
        direction="LONG",
        entry_time=open_ts - 3600,
        st_colour="green",
        st_colour_change_time=open_ts,
        ema_price=3010,
        strike=3000,
        expiry="2026-07-24",
        option_symbol="P-ETH-3000-240726",
        premium_received=100,
        contract_value=0.01,
        lots=1,
    )

    def option_candle_lookup(symbol, bar_time):
        return 90.0, 80.0, 85.0

    closed = []
    remaining, reenter = _manage_open(
        trade,
        bar,
        closed,
        option_candle_lookup=option_candle_lookup,
        reenter_flag=False,
    )
    assert remaining is None
    assert reenter is True
    assert len(closed) == 1
    assert closed[0].exit_reason == "expiry_close"
    assert closed[0].exit_price == 85.0
    assert closed[0].lots == 1


def _bar_for_bracket(option_high, option_low, option_close):
    """A mid-session bar (no ST flip, well before expiry cutoff) for bracket tests."""
    open_ts = int(datetime(2026, 7, 20, 11, 30, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    st = SuperTrendPoint(
        time=open_ts,
        hl2=3000,
        atr=1,
        upper_band=3010,
        lower_band=2990,
        st_line=2990,
        direction=1,
        flipped=False,
    )
    bar = IndicatorBar(
        time=open_ts,
        open=3000,
        high=3010,
        low=2990,
        close=3005,
        ema=3010,
        st=st,
        st_colour="green",
        st_colour_change_time=open_ts,
    )
    trade = OpenTrade(
        direction="LONG",
        entry_time=open_ts - 3600,
        st_colour="green",
        st_colour_change_time=open_ts,
        ema_price=3010,
        strike=3000,
        expiry="2026-07-25",
        option_symbol="P-ETH-3000-250726",
        premium_received=100,
        contract_value=0.01,
        lots=1,
        breakeven_decay_pct=0.0,
    )
    return bar, trade, lambda symbol, bar_time: (option_high, option_low, option_close)


def test_manage_open_respects_custom_stop_loss_pct():
    # Premium high 160 (60% rise). Default 105% would not stop; 50% does.
    bar, trade, lookup = _bar_for_bracket(160.0, 90.0, 140.0)
    closed = []
    remaining, _ = _manage_open(
        trade, bar, closed, option_candle_lookup=lookup, reenter_flag=False,
        stop_loss_pct=50, take_profit_pct=95,
    )
    assert remaining is None
    assert closed[0].exit_reason == "stop_loss"
    assert closed[0].exit_price == 150.0


def test_manage_open_respects_custom_take_profit_pct():
    # Premium low 35 (65% melt). Default 95% would not book; 60% does.
    bar, trade, lookup = _bar_for_bracket(110.0, 35.0, 45.0)
    closed = []
    remaining, reenter = _manage_open(
        trade, bar, closed, option_candle_lookup=lookup, reenter_flag=False,
        stop_loss_pct=105, take_profit_pct=60,
    )
    assert remaining is None
    assert reenter is True
    assert closed[0].exit_reason == "take_profit"
    assert closed[0].exit_price == 40.0


def test_formation_gate_blocks_same_colour_until_change():
    assert formation_blocks_entry(enabled=False, blocked_colour="green", current_colour="green") is False
    assert formation_blocks_entry(enabled=True, blocked_colour=None, current_colour="green") is False
    assert formation_blocks_entry(enabled=True, blocked_colour="green", current_colour="green") is True
    assert formation_blocks_entry(enabled=True, blocked_colour="green", current_colour="red") is False
    assert clear_formation_block(blocked_colour="green", current_colour="green") == "green"
    assert clear_formation_block(blocked_colour="green", current_colour="red") is None


def test_skip_setups_after_take_profit_counter():
    assert arm_skip_after_take_profit(exit_reason="take_profit", skip_n=1) == 1
    assert arm_skip_after_take_profit(exit_reason="take_profit", skip_n=2) == 2
    assert arm_skip_after_take_profit(exit_reason="take_profit", skip_n=0) is None
    assert arm_skip_after_take_profit(exit_reason="stop_loss", skip_n=1) is None
    assert arm_skip_after_take_profit(exit_reason="st_flip", skip_n=1) is None

    skip, left = consume_skip_setup(1)
    assert skip is True and left == 0
    skip, left = consume_skip_setup(2)
    assert skip is True and left == 1
    skip, left = consume_skip_setup(0)
    assert skip is False and left == 0


def test_pair_hedge_helpers():
    from cryptobridge.utils.st_options_pair_hedge import (
        hedge_stop_premium,
        opposite_option_side,
        pair_premiums_equal,
        should_open_decay_hedge,
    )

    assert opposite_option_side("PUT") == "CALL"
    assert opposite_option_side("CALL") == "PUT"
    assert pair_premiums_equal(50, 50) is True
    assert pair_premiums_equal(50, 51) is True  # tol >= 1
    assert pair_premiums_equal(50, 52.1) is False
    assert should_open_decay_hedge(100, 60, 40) is True  # 40% melt
    assert should_open_decay_hedge(100, 70, 40) is False
    # User example: entry 400, main profit $200, maxRisk $75, cv×lots = 1 → 675
    assert hedge_stop_premium(400, 200, 75, 1.0, 1) == 675.0
    # Unit-safe with cv×lots = 0.1 → premium rise of 2750
    assert hedge_stop_premium(400, 200, 75, 0.001, 100) == 3150.0
    assert hedge_stop_premium(400, -100, 75, 1.0, 1) is None  # budget ≤ 0
    assert hedge_stop_premium(400, 200, 75, 0.0, 1) is None


def test_manage_open_immediate_pair_sl_closes_both():
    bar, trade, _ = _bar_for_bracket(160.0, 90.0, 140.0)
    trade.pair_id = "pair-1"
    trade.pair_hedge_mode = "immediate"
    trade.main_option_side = "PUT"
    trade.hedge_symbol = "C-ETH-3000-250726"
    trade.hedge_premium_received = 80.0
    trade.hedge_entry_time = trade.entry_time
    trade.hedge_pending = False

    def lookup(symbol, bar_time):
        if str(symbol).startswith("C-"):
            return 90.0, 70.0, 85.0
        return 160.0, 90.0, 140.0

    closed = []
    remaining, reenter = _manage_open(
        trade, bar, closed, option_candle_lookup=lookup, reenter_flag=False,
        stop_loss_pct=50, take_profit_pct=95,
    )
    assert remaining is None
    assert reenter is False
    assert len(closed) == 2
    assert closed[0].leg_role == "main"
    assert closed[0].exit_reason == "stop_loss"
    assert closed[1].leg_role == "hedge"
    assert closed[1].exit_reason == "pair_stop"
    assert closed[1].option_symbol == "C-ETH-3000-250726"


def test_manage_open_immediate_pair_parity_and_skips_solo_tp():
    # Main low would hit 60% TP, but immediate pair disables solo TP; parity closes both.
    bar, trade, _ = _bar_for_bracket(110.0, 35.0, 50.0)
    trade.pair_id = "pair-2"
    trade.pair_hedge_mode = "immediate"
    trade.main_option_side = "PUT"
    trade.hedge_symbol = "C-ETH-3000-250726"
    trade.hedge_premium_received = 55.0
    trade.hedge_entry_time = trade.entry_time

    def lookup(symbol, bar_time):
        if str(symbol).startswith("C-"):
            return 55.0, 49.0, 50.0  # ≈ main close 50 → parity
        return 110.0, 35.0, 50.0

    closed = []
    remaining, reenter = _manage_open(
        trade, bar, closed, option_candle_lookup=lookup, reenter_flag=False,
        stop_loss_pct=105, take_profit_pct=60,
    )
    assert remaining is None
    assert reenter is False
    assert len(closed) == 2
    assert closed[0].exit_reason == "pair_parity"
    assert closed[1].exit_reason == "pair_parity"


def test_manage_open_decay_opens_hedge_then_tp_closes_both():
    bar, trade, _ = _bar_for_bracket(110.0, 35.0, 45.0)
    trade.pair_id = "pair-3"
    trade.pair_hedge_mode = "on_decay"
    trade.pair_hedge_decay_pct = 40.0
    trade.main_option_side = "PUT"
    trade.hedge_symbol = "C-ETH-3000-250726"
    trade.hedge_pending = True
    # 55% melt from 100 → 45 triggers decay open; low 35 hits 60% TP

    def lookup(symbol, bar_time):
        if str(symbol).startswith("C-"):
            return 70.0, 60.0, 65.0
        return 110.0, 35.0, 45.0

    closed = []
    remaining, reenter = _manage_open(
        trade, bar, closed, option_candle_lookup=lookup, reenter_flag=False,
        stop_loss_pct=105, take_profit_pct=60,
    )
    assert remaining is None
    assert reenter is True
    assert len(closed) == 2
    assert closed[0].exit_reason == "take_profit"
    assert closed[1].exit_reason == "pair_stop"
    assert closed[1].premium_received == 65.0

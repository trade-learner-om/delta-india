"""Breakeven trail after premium decay in ST Options backtest manage path."""

from cryptobridge.utils.st_options_backtest import OpenTrade, _manage_open
from cryptobridge.utils.st_options_indicators import IndicatorBar
from cryptobridge.utils.st_options_indicators import SuperTrendPoint


def _bar(time: int = 1_700_000_000) -> IndicatorBar:
    st = SuperTrendPoint(
        time=time,
        hl2=100,
        atr=1,
        upper_band=105,
        lower_band=95,
        st_line=98,
        direction=1,
        flipped=False,
    )
    return IndicatorBar(
        time=time,
        open=100,
        high=101,
        low=99,
        close=100.5,
        ema=102,
        st=st,
        st_colour="green",
        st_colour_change_time=time,
    )


def test_backtest_moves_sl_to_breakeven_then_stops():
    candles = {
        # First bar: decay to 60 (40% melt) → move BE; high stays below entry
        1_700_000_000: (70.0, 60.0, 62.0),
        # Second bar: premium spikes back to entry → BE stop
        1_700_003_600: (100.5, 90.0, 95.0),
    }

    def lookup(symbol: str, t: int):
        return candles[t]

    trade = OpenTrade(
        direction="LONG",
        entry_time=1_700_000_000,
        st_colour="green",
        st_colour_change_time=1_700_000_000,
        ema_price=102,
        strike=60000,
        expiry="2026-07-28",
        option_symbol="P-BTC-60000-280726",
        premium_received=100.0,
        contract_value=0.001,
        lots=1,
        stop_loss_pct=105.0,
        breakeven_decay_pct=40.0,
    )
    closed = []
    trade, _ = _manage_open(
        trade,
        _bar(1_700_000_000),
        closed,
        option_candle_lookup=lookup,
        reenter_flag=False,
        take_profit_pct=95,
    )
    assert trade is not None
    assert trade.sl_moved_to_breakeven is True
    assert trade.stop_loss_pct == 0.0
    assert closed == []

    trade, _ = _manage_open(
        trade,
        _bar(1_700_003_600),
        closed,
        option_candle_lookup=lookup,
        reenter_flag=False,
        take_profit_pct=95,
    )
    assert trade is None
    assert len(closed) == 1
    assert closed[0].exit_reason == "stop_loss"
    assert closed[0].exit_price == 100.0


def test_backtest_decay_zero_does_not_move_be():
    candles = {1_700_000_000: (70.0, 50.0, 55.0)}

    def lookup(symbol: str, t: int):
        return candles[t]

    trade = OpenTrade(
        direction="LONG",
        entry_time=1_700_000_000,
        st_colour="green",
        st_colour_change_time=1_700_000_000,
        ema_price=102,
        strike=60000,
        expiry="2026-07-28",
        option_symbol="P-BTC-60000-280726",
        premium_received=100.0,
        contract_value=0.001,
        lots=1,
        stop_loss_pct=105.0,
        breakeven_decay_pct=0.0,
    )
    closed = []
    trade, _ = _manage_open(
        trade,
        _bar(1_700_000_000),
        closed,
        option_candle_lookup=lookup,
        reenter_flag=False,
        take_profit_pct=95,
    )
    assert trade is not None
    assert trade.sl_moved_to_breakeven is False
    assert trade.stop_loss_pct == 105.0

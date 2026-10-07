from datetime import datetime, timezone

from cryptobridge.delta.market_data import LiveTicker
from cryptobridge.services.snapshot_service import live_tick_dict


def test_live_tick_dict_omits_null_quote_fields():
    ticker = LiveTicker(
        symbol="BTCUSD",
        last_price=None,
        mark_price=65000.0,
        bid=None,
        ask=None,
        change_24h=None,
        updated_at=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
    )
    tick = live_tick_dict(ticker)
    assert tick["price"] == 65000.0
    assert tick["mark_price"] == 65000.0
    assert "bid" not in tick
    assert "ask" not in tick
    assert "change24h" not in tick


def test_live_tick_dict_includes_bid_ask_when_present():
    ticker = LiveTicker(
        symbol="ETHUSD",
        last_price=None,
        mark_price=None,
        bid=3400.0,
        ask=3401.0,
        change_24h=0.5,
        updated_at=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
    )
    tick = live_tick_dict(ticker)
    assert tick["bid"] == 3400.0
    assert tick["ask"] == 3401.0
    assert tick["price"] == 3400.5
    assert tick["change24h"] == 0.5

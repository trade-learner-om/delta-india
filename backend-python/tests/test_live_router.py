from datetime import datetime, timezone

from cryptobridge.delta.market_data import LiveTicker
from cryptobridge.routers.live import _build_price_message, _tick_has_price
from cryptobridge.services.snapshot_service import display_price_from_ticker


class _SnapshotStub:
    def price_update_from(self, ticker: LiveTicker) -> dict:
        price = display_price_from_ticker(ticker)
        return {
            "type": "price",
            "symbol": ticker.symbol,
            "tick": {
                "symbol": ticker.symbol,
                "price": price,
                "mark_price": ticker.mark_price,
                "bid": ticker.bid,
                "ask": ticker.ask,
            },
        }


def test_tick_has_price_accepts_mark_bid_or_ask():
    assert _tick_has_price({"mark_price": 100.0})
    assert _tick_has_price({"bid": 99.0})
    assert not _tick_has_price({"mark_price": 0})


def test_build_price_message_sets_topic_and_tick():
    ticker = LiveTicker(
        symbol="BTCUSD",
        last_price=65000.0,
        mark_price=65010.0,
        bid=64990.0,
        ask=65020.0,
        change_24h=1.2,
        updated_at=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
    )
    message = _build_price_message(ticker, _SnapshotStub())
    assert message is not None
    assert message["topic"] == "price"
    assert message["symbol"] == "BTCUSD"
    assert message["tick"]["mark_price"] == 65010.0

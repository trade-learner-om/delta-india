from cryptobridge.utils.positions_helpers import forex_order_view, forex_position_view


def test_forex_position_view_keeps_broker_pnl():
    view = forex_position_view(
        {
            "ticket": 10,
            "symbol": "EURUSD",
            "side": "LONG",
            "size": 0.2,
            "entryPrice": 1.1,
            "markPrice": 1.12,
            "unrealizedPnl": 40,
        },
        "acct",
        "IC Markets 1",
    )
    assert view["venue"] == "forex"
    assert view["accountName"] == "IC Markets 1"
    assert view["side"] == "LONG"
    assert view["signedSize"] == 0.2
    assert view["contractValue"] is None
    assert view["unrealizedPnlUsd"] == 40


def test_forex_views_drop_empty_rows():
    assert forex_position_view({"symbol": "EURUSD", "size": 0, "side": "LONG"}, "acct", "A") is None
    assert forex_order_view({"symbol": "", "ticket": 1}, "acct", "A") is None


def test_forex_order_view():
    view = forex_order_view(
        {"ticket": 7, "symbol": "XAUUSD", "side": "SELL", "orderType": "limit", "price": 2400, "size": 0.1},
        "acct",
        "Forex",
    )
    assert view["status"] == "pending"
    assert view["orderType"] == "limit"
    assert view["price"] == 2400
    assert view["venue"] == "forex"

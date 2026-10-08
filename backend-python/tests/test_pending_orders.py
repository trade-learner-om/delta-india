from cryptobridge.utils.pending_orders import delta_edit_price_key, mt5_volume_replaces


def test_limit_orders_edit_the_limit_price():
    assert delta_edit_price_key("limit_order", None, 100, None) == "limit_price"


def test_stop_orders_edit_the_stop_price():
    assert delta_edit_price_key("market_order", "stop_loss_order", None, 90) == "stop_price"


def test_mt5_keeps_the_order_when_size_is_unchanged():
    assert mt5_volume_replaces(0.1, 0.1) is False
    assert mt5_volume_replaces(0.1, None) is False
    assert mt5_volume_replaces(0.1, 0.2) is True

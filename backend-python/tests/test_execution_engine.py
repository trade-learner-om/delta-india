from datetime import datetime, timezone

from cryptobridge.delta.market_data import LiveTicker
from cryptobridge.services.execution_engine import (
    condition_met,
    default_operators_for_option,
    is_call_option,
    monitor_to_view,
    trigger_price_from_ticker,
)
from cryptobridge.delta.rest_client import ProductSummary


def test_condition_met_gte_and_lte():
    assert condition_met(101.0, 100.0, "gte")
    assert not condition_met(99.0, 100.0, "gte")
    assert condition_met(99.0, 100.0, "lte")
    assert not condition_met(101.0, 100.0, "lte")


def test_trigger_price_prefers_last_price():
    ticker = LiveTicker(
        symbol="BTCUSD",
        last_price=65000.0,
        mark_price=64990.0,
        bid=64980.0,
        ask=65010.0,
        change_24h=None,
        updated_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
    )
    assert trigger_price_from_ticker(ticker) == 65000.0


def test_default_operators_for_call_and_put():
    call = ProductSummary(
        symbol="C-BTC-90000-310725",
        product_id=1,
        contract_value=0.001,
        tick_size=0.5,
        contract_unit_currency="BTC",
        quoting_asset="USD",
        contract_type="call_options",
    )
    put = ProductSummary(
        symbol="P-ETH-3000-310725",
        product_id=2,
        contract_value=0.01,
        tick_size=0.05,
        contract_unit_currency="ETH",
        quoting_asset="USD",
        contract_type="put_options",
    )
    assert default_operators_for_option(call) == ("gte", "gte")
    assert default_operators_for_option(put) == ("lte", "lte")
    assert is_call_option(call) is True
    assert is_call_option(put) is False


def test_monitor_to_view_serializes_id():
    doc = {
        "_id": "abc123",
        "optionSymbol": "C-BTC-90000-310725",
        "status": "Pending Trigger",
        "quantityLots": 10,
    }
    view = monitor_to_view(doc)
    assert view["id"] == "abc123"
    assert view["optionSymbol"] == "C-BTC-90000-310725"

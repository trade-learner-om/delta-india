from __future__ import annotations

import pytest

from cryptobridge.utils.positions_helpers import (
    delta_position_view,
    enrich_broker_position_mark,
    group_orders_by_broker,
    is_open_order_status,
    position_watch_symbols,
)


def test_delta_position_view_long():
    view = delta_position_view(
        {"product_symbol": "BTCUSD", "size": 2, "entry_price": 60000, "unrealized_pnl": 10},
        "acc1",
    )
    assert view is not None
    assert view["side"] == "LONG"
    assert view["broker"] == "delta"
    assert view["size"] == 2


def test_delta_option_long_pnl_matches_exchange_ui():
    view = delta_position_view(
        {
            "product_symbol": "P-BTC-59000-100726",
            "size": 100,
            "entry_price": 1776.0,
            "mark_price": 1873.3,
            "unrealized_pnl": -186.2,
        },
        "acc1",
    )
    assert view is not None
    assert view["side"] == "LONG"
    assert view["unrealizedPnlUsd"] == pytest.approx(9.73, abs=0.01)
    assert view["brokerUnrealizedPnl"] == pytest.approx(-186.2, abs=0.01)


def test_delta_option_short_pnl_matches_exchange_ui():
    view = delta_position_view(
        {
            "product_symbol": "C-BTC-59500-030726",
            "size": -80,
            "entry_price": 1240.0,
            "mark_price": 540.2,
            "unrealized_pnl": 44.08,
        },
        "acc1",
    )
    assert view is not None
    assert view["side"] == "SHORT"
    assert view["unrealizedPnlUsd"] == pytest.approx(55.984, abs=0.01)
    assert view["brokerUnrealizedPnl"] == pytest.approx(44.08, abs=0.01)


def test_delta_option_uses_explicit_contract_value():
    view = delta_position_view(
        {
            "product_symbol": "C-ETH-3000-100726",
            "size": 10,
            "entry_price": 50.0,
            "mark_price": 60.0,
            "contract_value": 0.01,
        },
        "acc1",
    )
    assert view is not None
    assert view["unrealizedPnlUsd"] == pytest.approx((60 - 50) * 0.01 * 10)


def test_delta_option_falls_back_to_mark_based_pnl_without_exchange_pnl():
    view = delta_position_view(
        {
            "product_symbol": "C-BTC-59500-030726",
            "size": -80,
            "entry_price": 1240.0,
            "mark_price": 540.2,
        },
        "acc1",
    )
    assert view is not None
    assert view["unrealizedPnlUsd"] == pytest.approx(55.984, abs=0.01)


def test_is_open_order_status():
    assert is_open_order_status("PENDING")
    assert not is_open_order_status("CLOSED")


def test_group_orders_by_broker():
    orders = [
        {"broker": "delta", "createdAt": "2026-01-02"},
        {"broker": "delta", "createdAt": "2026-01-04"},
    ]
    grouped = group_orders_by_broker(orders)
    assert len(grouped["delta"]) == 2
    assert grouped["delta"][0]["createdAt"] == "2026-01-04"


def test_position_watch_symbols_includes_underlying_index():
    symbols = position_watch_symbols([
        {"symbol": "C-BTC-59000-100726", "coin": "BTC"},
        {"symbol": "ETHUSD", "coin": "ETH"},
    ])
    assert symbols == {"C-BTC-59000-100726", "BTCUSD", "ETHUSD"}


def test_enrich_broker_position_mark_overlays_live_ticker():
    from types import SimpleNamespace

    tickers = {
        "C-BTC-59000-100726": SimpleNamespace(
            mark_price=540.2, last_price=None, bid=None, ask=None,
        ),
    }
    enriched = enrich_broker_position_mark(
        {"product_symbol": "C-BTC-59000-100726", "mark_price": 500.0, "size": -1},
        tickers,
    )
    assert enriched["mark_price"] == 540.2

import pytest
from fastapi import HTTPException

from cryptobridge.utils.order_prices import validate_order_prices


def test_buy_accepts_stop_below_and_target_above():
    validate_order_prices("BUY", 100, 90, 120)


def test_sell_accepts_stop_above_and_skips_empty_target():
    validate_order_prices("SELL", 100, 110, None)


def test_buy_rejects_stop_above_entry():
    with pytest.raises(HTTPException, match="below entry"):
        validate_order_prices("BUY", 100, 110, None)


def test_sell_rejects_target_above_entry():
    with pytest.raises(HTTPException, match="below entry"):
        validate_order_prices("SELL", 100, 110, 130)


def test_rejects_non_positive_prices():
    with pytest.raises(HTTPException, match="greater than 0"):
        validate_order_prices("BUY", 0, 1, None)
    with pytest.raises(HTTPException, match="greater than 0"):
        validate_order_prices("BUY", 100, 90, 0)

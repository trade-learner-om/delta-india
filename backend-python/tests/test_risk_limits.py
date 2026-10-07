import pytest
from fastapi import HTTPException

from cryptobridge.utils.risk_limits import (
    LOW_MARGIN_CAP,
    assert_risk_within_cap,
    max_risk_amount,
)


def test_max_risk_below_threshold():
    assert max_risk_amount(999.99) == LOW_MARGIN_CAP
    assert max_risk_amount(100) == LOW_MARGIN_CAP
    assert max_risk_amount(0) == 0.0


def test_max_risk_at_and_above_threshold():
    assert max_risk_amount(1000) == 10.0
    assert max_risk_amount(5000) == 50.0


def test_assert_risk_within_cap_rejects_over():
    with pytest.raises(HTTPException) as exc:
        assert_risk_within_cap(11, 500)
    assert "max risk" in str(exc.value.detail).lower()


def test_assert_risk_within_cap_allows_at_cap():
    assert_risk_within_cap(10, 500)
    assert_risk_within_cap(50, 5000)

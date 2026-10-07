from __future__ import annotations

import pytest

from cryptobridge.utils.risk_sizing import RiskSizingError, compute_position_size


def test_compute_position_size_from_risk_and_sl_distance():
    # risk 100, distance 10, contract_value 1 -> floor(100/10) = 10
    assert compute_position_size(100.0, 1000.0, 990.0, 1.0) == 10.0


def test_compute_position_size_uses_contract_value():
    assert compute_position_size(100.0, 100.0, 90.0, 2.0) == 5.0


def test_compute_position_size_minimum_one():
    # floor(0.05 / 0.1) = 0 -> clamped to 1 contract
    assert compute_position_size(0.05, 100.0, 99.9, 1.0) == 1.0


def test_rejects_missing_risk():
    with pytest.raises(RiskSizingError):
        compute_position_size(None, 100.0, 90.0, 1.0)


def test_rejects_zero_sl_distance():
    with pytest.raises(RiskSizingError):
        compute_position_size(100.0, 100.0, 100.0, 1.0)

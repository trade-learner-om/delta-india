from __future__ import annotations

MARGIN_THRESHOLD = 1000.0
LOW_MARGIN_CAP = 10.0
HIGH_MARGIN_RATE = 0.01


def max_risk_amount(available_margin: float | None) -> float:
    """Max risk: $10 when margin < $1,000; else 1% of available margin."""
    margin = float(available_margin or 0)
    if margin <= 0:
        return 0.0
    if margin < MARGIN_THRESHOLD:
        return LOW_MARGIN_CAP
    return margin * HIGH_MARGIN_RATE


def max_risk_cap_description() -> str:
    return "max $10 when available margin is below $1,000, otherwise 1% of available margin"


def assert_risk_within_cap(risk_amount: float, available_margin: float | None) -> None:
    from cryptobridge.exceptions import http_error

    cap = max_risk_amount(available_margin)
    risk = float(risk_amount or 0)
    if risk <= 0:
        raise http_error(400, "Risk amount must be greater than 0.")
    if cap <= 0:
        raise http_error(400, "Available balance is required to size risk.")
    if risk > cap:
        raise http_error(
            400,
            f"Risk amount cannot exceed max risk ({cap:.2f}). {max_risk_cap_description()}.",
        )

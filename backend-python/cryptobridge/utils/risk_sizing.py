from __future__ import annotations

import math


class RiskSizingError(ValueError):
    pass


def compute_position_size(
    risk_amount: float | None,
    entry: float | None,
    stop_loss: float | None,
    contract_value: float | None,
) -> float:
    """Size contracts from risk budget and entry-to-SL distance."""
    risk = float(risk_amount or 0)
    if risk <= 0:
        raise RiskSizingError("Risk amount must be greater than 0.")

    entry_value = float(entry or 0)
    stop_value = float(stop_loss or 0)
    distance = abs(entry_value - stop_value)
    if distance <= 0:
        raise RiskSizingError("Stop loss must be different from entry to size the position.")

    unit = float(contract_value) if contract_value and contract_value > 0 else 1.0
    return max(1.0, math.floor(risk / (distance * unit)))

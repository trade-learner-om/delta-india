from __future__ import annotations

from typing import Any

from cryptobridge.exceptions import http_error


def _price(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_order_prices(side: str, entry: Any, stop_loss: Any, target: Any = None) -> None:
    """Entry and stop are required. Target is checked only when a price is sent."""
    label = "sell" if str(side or "").upper() == "SELL" else "buy"
    entry_price = _price(entry)
    stop_price = _price(stop_loss)
    if entry_price is None or entry_price <= 0 or stop_price is None or stop_price <= 0:
        raise http_error(400, "Entry and stop loss must be greater than 0.")
    if label == "sell":
        if stop_price <= entry_price:
            raise http_error(400, "Stop loss must be above entry for a sell.")
    elif stop_price >= entry_price:
        raise http_error(400, "Stop loss must be below entry for a buy.")
    target_price = _price(target)
    if target_price is None:
        return
    if target_price <= 0:
        raise http_error(400, "Target must be greater than 0.")
    if label == "sell" and target_price >= entry_price:
        raise http_error(400, "Target must be below entry for a sell.")
    if label == "buy" and target_price <= entry_price:
        raise http_error(400, "Target must be above entry for a buy.")

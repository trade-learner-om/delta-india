from __future__ import annotations


def delta_edit_price_key(
    order_type: str,
    stop_order_type: str | None,
    limit_price: float | None,
    stop_price: float | None,
) -> str:
    """Choose the Delta field that the pending-order price edits."""
    text = f"{order_type or ''} {stop_order_type or ''}".lower()
    has_limit = limit_price not in (None, "", 0)
    if "limit" in text and "stop" not in text:
        return "limit_price"
    if "stop" in text and "limit" in text and has_limit:
        return "limit_price"
    if "stop" in text or (stop_price not in (None, "", 0) and not has_limit):
        return "stop_price"
    return "limit_price"


def mt5_volume_replaces(current_volume: float, requested_size: float | None) -> bool:
    if requested_size is None:
        return False
    return abs(float(current_volume) - float(requested_size)) > 1e-8

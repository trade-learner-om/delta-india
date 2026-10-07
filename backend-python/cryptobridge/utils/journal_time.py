from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def to_ist_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=IST)
    return value.astimezone(IST).isoformat()


def delta_time_to_ist(value) -> str | None:
    """Delta clocks are already IST. Attach that zone, and do not add another offset.

    A unix instant is an absolute moment, so it is only displayed in IST.
    A naive clock string is read as IST wall time.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return to_ist_iso(value)
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        raw = int(float(value))
        if raw > 10_000_000_000_000:
            raw = raw // 1_000_000
        elif raw > 10_000_000_000:
            raw = raw // 1_000
        if raw <= 0:
            return None
        return datetime.fromtimestamp(raw, tz=timezone.utc).astimezone(IST).isoformat()
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST).isoformat()


def mt5_server_time_to_ist(server_epoch: int | None, offset_seconds: int | None) -> str | None:
    """MT5 deal times use the broker server clock. Shift by the stored UTC offset, then to IST."""
    try:
        epoch = int(server_epoch or 0)
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    try:
        offset = int(offset_seconds or 0)
    except (TypeError, ValueError):
        offset = 0
    instant = datetime.fromtimestamp(epoch - offset, tz=timezone.utc)
    return instant.astimezone(IST).isoformat()

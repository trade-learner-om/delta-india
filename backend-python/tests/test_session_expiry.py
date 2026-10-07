from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cryptobridge.services.auth_service import next_saturday_midnight_ist

IST = ZoneInfo("Asia/Kolkata")


def _ist(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=IST)


def test_monday_login_lasts_until_the_coming_saturday():
    expires = next_saturday_midnight_ist(_ist(2026, 10, 5, 12, 0))
    assert expires.astimezone(IST) == _ist(2026, 10, 10)


def test_login_after_saturday_starts_lasts_until_the_following_saturday():
    expires = next_saturday_midnight_ist(_ist(2026, 10, 10, 0, 1))
    assert expires.astimezone(IST) == _ist(2026, 10, 17)


def test_exact_saturday_midnight_is_not_already_expired():
    expires = next_saturday_midnight_ist(_ist(2026, 10, 10))
    assert expires.astimezone(IST) == _ist(2026, 10, 17)
    assert expires > _ist(2026, 10, 10).astimezone(timezone.utc)

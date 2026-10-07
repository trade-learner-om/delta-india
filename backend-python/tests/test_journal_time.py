from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cryptobridge.utils.journal_time import delta_time_to_ist, mt5_server_time_to_ist

IST = ZoneInfo("Asia/Kolkata")


def test_naive_delta_clock_stays_on_the_ist_wall():
    assert delta_time_to_ist("2026-10-07T15:30:00") == datetime(2026, 10, 7, 15, 30, tzinfo=IST).isoformat()


def test_delta_unix_instant_is_shown_in_ist():
    # 2026-10-07 10:00:00 UTC == 15:30 IST
    epoch = int(datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc).timestamp())
    assert delta_time_to_ist(epoch) == datetime(2026, 10, 7, 15, 30, tzinfo=IST).isoformat()


def test_mt5_server_clock_shifts_by_the_broker_offset():
    # Server clock is two hours ahead of UTC. 12:00 server == 10:00 UTC == 15:30 IST.
    server_epoch = int(datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc).timestamp())
    offset = 2 * 60 * 60
    assert mt5_server_time_to_ist(server_epoch, offset) == datetime(2026, 10, 7, 15, 30, tzinfo=IST).isoformat()

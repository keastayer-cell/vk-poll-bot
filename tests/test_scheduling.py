from datetime import datetime

from vk_poll_bot.scheduling import is_poll_time


def test_default_schedule_is_monday_and_thursday_at_eight() -> None:
    assert is_poll_time(datetime(2026, 9, 21, 8, 0))
    assert is_poll_time(datetime(2026, 9, 24, 8, 0))


def test_default_schedule_rejects_other_day_or_time() -> None:
    assert not is_poll_time(datetime(2026, 9, 22, 8, 0))
    assert not is_poll_time(datetime(2026, 9, 24, 8, 1))

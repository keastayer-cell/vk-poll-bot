import asyncio
from datetime import datetime

from vk_poll_bot.scheduling import ScheduleManager, is_poll_time


def test_default_schedule_is_monday_and_thursday_at_eight() -> None:
    assert is_poll_time(datetime(2026, 9, 21, 8, 0))
    assert is_poll_time(datetime(2026, 9, 24, 8, 0))


def test_default_schedule_rejects_other_day_or_time() -> None:
    assert not is_poll_time(datetime(2026, 9, 22, 8, 0))
    assert not is_poll_time(datetime(2026, 9, 24, 8, 1))


class FakeScheduledService:
    def __init__(self):
        self.schedule = {
            "poll_days": "mon,thu",
            "poll_hour": 8,
            "poll_minute": 0,
            "deadline_days": "mon,thu",
            "deadline_hour": 15,
            "deadline_minute": 0,
            "close_days": "mon,thu",
            "close_hour": 20,
            "close_minute": 0,
            "reminder_days": "mon,thu",
            "reminder_hour": 19,
            "reminder_minute": 0,
        }
        self.poll = None
        self.calls = []

    async def create_poll(self, poll_date=None):
        self.calls.append(("poll", poll_date))
        self.poll = {"poll_date": poll_date, "is_open": True}

    async def check_deadline(self):
        self.calls.append(("deadline", None))

    async def remind_game(self):
        self.calls.append(("reminder", None))

    async def close_poll(self):
        self.calls.append(("close", None))

    def schedule_text(self):
        return "schedule"


def test_reconcile_runs_missed_jobs_in_order() -> None:
    service = FakeScheduledService()
    manager = ScheduleManager(service, "Europe/Moscow")

    asyncio.run(manager.reconcile(datetime(2026, 9, 24, 19, 30)))

    assert service.calls == [
        ("poll", "2026-09-24"),
        ("deadline", None),
        ("reminder", None),
    ]

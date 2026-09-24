from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

JOB_KEYS = ("poll", "deadline", "close", "remind_mon", "remind_thu")


def is_scheduled_day(now: datetime, days: str) -> bool:
    return now.strftime("%a").lower()[:3] in {day.strip() for day in days.split(",")}


def scheduled_at(now: datetime, hour: int, minute: int) -> datetime:
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def is_poll_time(
    now: datetime,
    *,
    days: str = "mon,thu",
    hour: int = 8,
    minute: int = 0,
) -> bool:
    return is_scheduled_day(now, days) and (now.hour, now.minute) == (hour, minute)


class ScheduleManager:
    def __init__(self, service, timezone: str, logger: logging.Logger | None = None):
        self.service = service
        self.timezone = timezone
        self.logger = logger or logging.getLogger(__name__)
        self.scheduler = AsyncIOScheduler(timezone=timezone)

    def reschedule(self) -> None:
        callbacks = {
            "poll": (self.service.create_poll, []),
            "deadline": (self.service.check_deadline, []),
            "close": (self.service.close_poll, []),
            "remind_mon": (self.service.remind_game, ["remind_mon"]),
            "remind_thu": (self.service.remind_game, ["remind_thu"]),
        }
        for key in JOB_KEYS:
            try:
                self.scheduler.remove_job(f"job_{key}")
            except JobLookupError:
                pass
            config = self.service.schedule
            self.scheduler.add_job(
                callbacks[key][0],
                "cron",
                id=f"job_{key}",
                args=callbacks[key][1],
                day_of_week=config[f"{key}_days"],
                hour=config[f"{key}_hour"],
                minute=config[f"{key}_minute"],
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
        self.logger.info("Расписание установлено: %s", self.service.schedule_text())

    async def reconcile(self, now: datetime | None = None) -> None:
        now = now or datetime.now(ZoneInfo(self.timezone))
        config = self.service.schedule
        poll_date = now.strftime("%Y-%m-%d")
        close_at = scheduled_at(now, config["close_hour"], config["close_minute"])
        close_today = is_scheduled_day(now, config["close_days"])
        before_close = not close_today or now < close_at
        poll_at = scheduled_at(now, config["poll_hour"], config["poll_minute"])
        if is_scheduled_day(now, config["poll_days"]) and poll_at <= now and before_close:
            await self.service.create_poll(poll_date=poll_date)
        poll = self.service.poll
        active_today = poll and poll.get("poll_date") == poll_date and poll.get("is_open")
        if active_today and before_close:
            deadline_at = scheduled_at(now, config["deadline_hour"], config["deadline_minute"])
            if is_scheduled_day(now, config["deadline_days"]) and deadline_at <= now:
                await self.service.check_deadline()
            for reminder_key in ("remind_mon", "remind_thu"):
                reminder_at = scheduled_at(
                    now,
                    config[f"{reminder_key}_hour"],
                    config[f"{reminder_key}_minute"],
                )
                if is_scheduled_day(now, config[f"{reminder_key}_days"]) and reminder_at <= now:
                    await self.service.remind_game(reminder_key)
        if active_today and close_today and close_at <= now:
            await self.service.close_poll()

    async def start(self) -> None:
        self.reschedule()
        self.scheduler.start()
        await self.reconcile()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

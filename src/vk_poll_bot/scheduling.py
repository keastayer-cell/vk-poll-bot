from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def register_poll_job(
    scheduler: AsyncIOScheduler,
    callback,
    *,
    days: str = "mon,thu",
    hour: int = 8,
    minute: int = 0,
) -> None:
    scheduler.add_job(
        callback,
        "cron",
        id="job_poll",
        day_of_week=days,
        hour=hour,
        minute=minute,
        replace_existing=True,
        misfire_grace_time=3600,
    )


def is_poll_time(
    now: datetime,
    *,
    days: str = "mon,thu",
    hour: int = 8,
    minute: int = 0,
) -> bool:
    configured_days = {day.strip() for day in days.split(",")}
    current_day = now.strftime("%a").lower()[:3]
    return current_day in configured_days and (now.hour, now.minute) == (hour, minute)

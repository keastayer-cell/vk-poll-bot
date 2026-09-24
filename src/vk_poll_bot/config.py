from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _integer(name: str, default: str = "0") -> int:
    raw = os.getenv(name, default).strip()
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"Переменная {name} должна быть целым числом") from error


def _int_list(name: str) -> tuple[int, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    try:
        return tuple(int(value.strip()) for value in raw.split(",") if value.strip())
    except ValueError as error:
        raise ValueError(f"Переменная {name} должна содержать ID через запятую") from error


def _time(name: str, default: str) -> tuple[int, int]:
    raw = os.getenv(name, default).strip()
    try:
        hour_text, minute_text = raw.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except ValueError as error:
        raise ValueError(f"{name} должен быть указан в формате ЧЧ:ММ") from error
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"{name} содержит недопустимое время")
    return hour, minute


def _days(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().lower()
    if not value or any(day.strip() not in VALID_DAYS for day in value.split(",")):
        raise ValueError(f"{name} должен содержать дни mon..sun через запятую")
    return value


@dataclass(frozen=True)
class Settings:
    group_token: str
    group_id: int
    peer_id: int
    api_version: str
    admin_ids: tuple[int, ...]
    timezone: str
    yes_threshold: int
    poll_question: str
    poll_days: str
    poll_hour: int
    poll_minute: int
    deadline_hour: int
    deadline_minute: int
    close_hour: int
    close_minute: int
    reminder_hour: int
    reminder_minute: int
    data_dir: Path
    enable_scheduler: bool

    @property
    def initial_schedule(self) -> dict:
        return {
            "poll_days": self.poll_days,
            "poll_hour": self.poll_hour,
            "poll_minute": self.poll_minute,
            "deadline_days": self.poll_days,
            "deadline_hour": self.deadline_hour,
            "deadline_minute": self.deadline_minute,
            "close_days": self.poll_days,
            "close_hour": self.close_hour,
            "close_minute": self.close_minute,
            "reminder_days": self.poll_days,
            "reminder_hour": self.reminder_hour,
            "reminder_minute": self.reminder_minute,
        }


def load_settings(base_dir: str | Path = ".") -> Settings:
    base_path = Path(base_dir).resolve()
    load_dotenv(base_path / ".env")
    token = os.getenv("VK_GROUP_TOKEN", "").strip()
    if not token:
        raise ValueError("Не задана переменная VK_GROUP_TOKEN")
    group_id = _integer("VK_GROUP_ID")
    if group_id <= 0:
        raise ValueError("VK_GROUP_ID должен быть положительным")
    threshold = _integer("YES_THRESHOLD", "10")
    if threshold < 1:
        raise ValueError("YES_THRESHOLD должен быть положительным")
    poll_hour, poll_minute = _time("POLL_TIME", "08:00")
    deadline_hour, deadline_minute = _time("DEADLINE_TIME", "15:00")
    close_hour, close_minute = _time("CLOSE_TIME", "20:00")
    reminder_hour, reminder_minute = _time("REMINDER_TIME", "19:00")
    data_dir_raw = os.getenv("DATA_DIR", ".").strip() or "."
    data_dir = Path(data_dir_raw)
    if not data_dir.is_absolute():
        data_dir = base_path / data_dir
    return Settings(
        group_token=token,
        group_id=group_id,
        peer_id=_integer("VK_PEER_ID"),
        api_version=os.getenv("VK_API_VERSION", "5.199").strip() or "5.199",
        admin_ids=_int_list("ADMIN_IDS"),
        timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow",
        yes_threshold=threshold,
        poll_question=os.getenv("POLL_QUESTION", "Идете?").strip() or "Идете?",
        poll_days=_days("POLL_DAYS", "mon,thu"),
        poll_hour=poll_hour,
        poll_minute=poll_minute,
        deadline_hour=deadline_hour,
        deadline_minute=deadline_minute,
        close_hour=close_hour,
        close_minute=close_minute,
        reminder_hour=reminder_hour,
        reminder_minute=reminder_minute,
        data_dir=data_dir.resolve(),
        enable_scheduler=os.getenv("ENABLE_SCHEDULER", "0").strip() == "1",
    )

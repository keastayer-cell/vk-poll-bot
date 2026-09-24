from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _required_int(name: str) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        raise ValueError(f"Не задана переменная {name}")
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
    data_dir: Path
    enable_scheduler: bool


def _poll_time() -> tuple[int, int]:
    raw = os.getenv("POLL_TIME", "08:00").strip()
    try:
        hour_text, minute_text = raw.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except ValueError as error:
        raise ValueError("POLL_TIME должен быть указан в формате ЧЧ:ММ") from error
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("POLL_TIME содержит недопустимое время")
    return hour, minute


def load_settings(base_dir: str | Path = ".") -> Settings:
    base_path = Path(base_dir).resolve()
    load_dotenv(base_path / ".env")
    token = os.getenv("VK_GROUP_TOKEN", "").strip()
    if not token:
        raise ValueError("Не задана переменная VK_GROUP_TOKEN")
    threshold = int(os.getenv("YES_THRESHOLD", "10"))
    if threshold < 1:
        raise ValueError("YES_THRESHOLD должен быть положительным")
    poll_days = os.getenv("POLL_DAYS", "mon,thu").strip().lower()
    valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    if not poll_days or any(day.strip() not in valid_days for day in poll_days.split(",")):
        raise ValueError("POLL_DAYS должен содержать дни mon..sun через запятую")
    poll_hour, poll_minute = _poll_time()
    data_dir_raw = os.getenv("DATA_DIR", ".").strip() or "."
    data_dir = Path(data_dir_raw)
    if not data_dir.is_absolute():
        data_dir = base_path / data_dir
    return Settings(
        group_token=token,
        group_id=_required_int("VK_GROUP_ID"),
        peer_id=_required_int("VK_PEER_ID"),
        api_version=os.getenv("VK_API_VERSION", "5.199").strip() or "5.199",
        admin_ids=_int_list("ADMIN_IDS"),
        timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow",
        yes_threshold=threshold,
        poll_question=os.getenv("POLL_QUESTION", "Идете?").strip() or "Идете?",
        poll_days=poll_days,
        poll_hour=poll_hour,
        poll_minute=poll_minute,
        data_dir=data_dir.resolve(),
        enable_scheduler=os.getenv("ENABLE_SCHEDULER", "0").strip() == "1",
    )

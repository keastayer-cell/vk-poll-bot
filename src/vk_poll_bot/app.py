from __future__ import annotations

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .api import BotsLongPoll, VkApiClient
from .config import load_settings
from .scheduling import ScheduleManager
from .service import PollService
from .storage import JsonStateRepository


def configure_logging(data_dir: Path) -> logging.Logger:
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                data_dir / "bot.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger("vk_poll_bot")


async def run(base_dir: Path, *, check: bool = False) -> None:
    settings = load_settings(base_dir)
    logger = configure_logging(settings.data_dir)
    api = VkApiClient(settings.group_token, settings.group_id, settings.api_version)
    repository = JsonStateRepository(settings.data_dir / "state.json")
    service = PollService(api, settings, repository, logger)
    scheduler = ScheduleManager(service, settings.timezone, logger)
    service.reschedule_callback = scheduler.reschedule
    try:
        server = await api.get_long_poll_server()
        logger.info("VK API доступен; Long Poll server=%s", server.server)
        if check:
            print("OK: VK API и Bots Long Poll доступны")
            return
        if settings.peer_id <= 0:
            logger.warning(
                "VK_PEER_ID=0: отправьте /where в тестовом чате и запишите peer_id в .env"
            )
        if settings.enable_scheduler:
            await scheduler.start()
        else:
            logger.info("Планировщик отключён; для теста используйте /poll")
        long_poll = BotsLongPoll(api, logger)
        async for event in long_poll.events():
            await service.handle_update(event)
    finally:
        scheduler.shutdown()
        await api.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="VK poll bot")
    parser.add_argument("--check", action="store_true", help="проверить токен и Long Poll")
    args = parser.parse_args()
    base_dir = Path(__file__).resolve().parents[2]
    asyncio.run(run(base_dir, check=args.check))

import asyncio
import json

from fakes import FakeApi, make_settings

from vk_poll_bot.service import PollService
from vk_poll_bot.storage import JsonStateRepository


def make_service(tmp_path, **settings_overrides):
    api = FakeApi()
    settings = make_settings(tmp_path, **settings_overrides)
    repository = JsonStateRepository(tmp_path / "state.json")
    return PollService(api, settings, repository), api


def test_create_poll_and_prevent_duplicate(tmp_path) -> None:
    async def scenario():
        bot, api = make_service(tmp_path)
        assert await bot.create_poll("2026-09-24") is True
        assert await bot.create_poll("2026-09-24") is False
        assert bot.poll["poll_date"] == "2026-09-24"
        assert api.pinned == [(2_000_000_001, 101, 0)]
        keyboard = json.loads(api.sent[0][2])
        assert keyboard["buttons"][0][0]["action"]["label"] == "✅ ИДУ"
        assert "Получить статистику: /status" in api.sent[0][1]
        chat_messages = [message for message in api.sent if message[0] == 2_000_000_001]
        assert len(chat_messages) == 2
        assert chat_messages[1][1].startswith("Я создал опрос — проголосуйте.")
        assert "+1 ФИО" in chat_messages[1][1]

    asyncio.run(scenario())


def test_vote_event_changes_existing_vote(tmp_path) -> None:
    async def scenario():
        bot, api = make_service(tmp_path)
        api.names[20] = "Иван Иванов"
        await bot.create_poll("2026-09-24")

        async def vote(choice):
            await bot.handle_vote_event(
                {
                    "object": {
                        "event_id": f"event-{choice}",
                        "user_id": 20,
                        "peer_id": 2_000_000_001,
                        "payload": {
                            "command": "vote",
                            "choice": choice,
                            "poll_date": "2026-09-24",
                        },
                    }
                }
            )

        await vote("yes")
        await vote("no")
        assert bot.poll["voters"]["20"] == {"name": "Иван Иванов", "choice": "no"}
        assert "Ваш голос: Нет" in api.answers[-1][-1]
        assert "Не идут (1)" in api.edited[-1][3]

    asyncio.run(scenario())


def test_plus_one_from_regular_chat_member(tmp_path) -> None:
    async def scenario():
        bot, api = make_service(tmp_path)
        api.names[20] = "Иван Иванов"
        await bot.create_poll("2026-09-24")
        await bot.handle_message_event(
            {
                "object": {
                    "message": {
                        "peer_id": 2_000_000_001,
                        "from_id": 20,
                        "text": "+1 Петров",
                    }
                }
            }
        )
        manual_votes = list(bot.poll["manual_yes_voters"].values())
        assert manual_votes[0]["label"] == "Петров"
        assert "Добавлен: Петров" in api.sent[-1][1]

    asyncio.run(scenario())


def test_admin_can_start_and_close_poll(tmp_path) -> None:
    async def scenario():
        bot, api = make_service(tmp_path)
        await bot.handle_message_event(
            {"object": {"message": {"peer_id": 2_000_000_001, "from_id": 10, "text": "/poll"}}}
        )
        await bot.handle_message_event(
            {"object": {"message": {"peer_id": 2_000_000_001, "from_id": 10, "text": "/close"}}}
        )
        assert bot.poll is None
        assert api.unpinned == [2_000_000_001]
        assert "Голосование закрыто" in api.sent[-1][1]

    asyncio.run(scenario())


def test_where_works_before_peer_is_configured(tmp_path) -> None:
    async def scenario():
        bot, api = make_service(tmp_path, peer_id=0)
        await bot.handle_message_event(
            {"object": {"message": {"peer_id": 2_000_000_099, "from_id": 55, "text": "/where"}}}
        )
        assert api.sent[-1][1] == "peer_id=2000000099\nuser_id=55"

    asyncio.run(scenario())


def test_outgoing_event_recovers_chat_message_ids(tmp_path) -> None:
    async def scenario():
        bot, api = make_service(tmp_path)
        await bot.create_poll("2026-09-24")
        random_id = bot.poll["random_id"]
        await bot.handle_outgoing_message(
            {
                "object": {
                    "message": {
                        "id": 77,
                        "conversation_message_id": 12,
                        "random_id": random_id,
                    }
                }
            }
        )
        assert bot.poll["message_id"] == 77
        assert bot.poll["conversation_message_id"] == 12
        assert api.pinned[-1] == (2_000_000_001, 77, 0)

    asyncio.run(scenario())


def test_admin_can_enable_private_notifications(tmp_path) -> None:
    async def scenario():
        bot, api = make_service(tmp_path)
        await bot.handle_message_event(
            {"object": {"message": {"peer_id": 10, "from_id": 10, "text": "/start"}}}
        )
        assert api.sent[-1][0] == 10
        assert "уведомления администратора включены" in api.sent[-1][1]

    asyncio.run(scenario())

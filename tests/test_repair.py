import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from fakes import FakeApi, make_settings

from vk_poll_bot.api import VkApiError
from vk_poll_bot.models import new_poll_state
from vk_poll_bot.service import PollService
from vk_poll_bot.storage import JsonStateRepository


def make_bot(tmp_path, api=None):
    bot = PollService(api or FakeApi(), make_settings(tmp_path),
                      JsonStateRepository(tmp_path / "state.json"))
    poll = new_poll_state("2026-11-19", "Идете?", bot.settings.peer_id)
    poll.update(message_id=0, conversation_message_id=123, show_roster=True)
    poll["voters"] = {"20": {"name": "Вымышленный игрок", "choice": "yes"}}
    poll["manual_yes_voters"] = {"manual:1": {"label": "Вымышленный гость"}}
    bot.state["current_poll"] = poll
    bot.save()
    return bot


async def command(bot, user=10, peer=None):
    await bot.handle_message_event({"object": {"message": {
        "peer_id": bot.settings.peer_id if peer is None else peer,
        "from_id": user, "text": "/repair",
    }}})


@pytest.mark.parametrize("private", [False, True])
@pytest.mark.parametrize("global_id", [0, 456])
def test_repair_same_poll_buttons_and_state_unchanged(tmp_path, private, global_id):
    async def scenario():
        bot = make_bot(tmp_path)
        bot.poll["message_id"] = global_id
        bot.save()
        before = deepcopy(bot.state)
        original_bytes = bot.repository.path.read_bytes()
        peer = 10 if private else bot.settings.peer_id
        await command(bot, peer=peer)
        assert len(bot.api.edited) == 1
        chat, mid, cmid, text, raw_keyboard = bot.api.edited[0]
        assert chat == bot.settings.peer_id
        assert (mid, cmid) == ((456, 0) if global_id else (0, 123))
        assert text == bot.render_poll()
        keyboard = json.loads(raw_keyboard)
        buttons = [b for row in keyboard["buttons"] for b in row]
        assert keyboard["inline"] is True
        assert len(buttons) == 4
        assert all(b["action"]["type"] == "callback" for b in buttons)
        assert {json.loads(b["action"]["payload"]).get("choice") for b in buttons} == {
            "yes", "no", "cancel", None}
        assert "СКРЫТЬ СОСТАВ" in buttons[-1]["action"]["label"]
        assert bot.state == before
        assert bot.repository.path.read_bytes() == original_bytes
        assert bot.api.sent[-1][0] == peer
        assert "Голоса и приглашённые сохранены" in bot.api.sent[-1][1]
        assert not bot.api.deleted and not bot.api.pinned
    asyncio.run(scenario())


@pytest.mark.parametrize("private", [False, True])
def test_non_admin_cannot_repair(tmp_path, private):
    async def scenario():
        bot = make_bot(tmp_path)
        await command(bot, user=20, peer=20 if private else bot.settings.peer_id)
        assert not bot.api.edited
        assert "только администратор" in bot.api.sent[-1][1]
    asyncio.run(scenario())


def test_repair_from_other_chat_is_ignored(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path)
        await command(bot, peer=2000000099)
        assert not bot.api.edited and not bot.api.sent
    asyncio.run(scenario())


@pytest.mark.parametrize("missing", ["poll", "closed", "message"])
def test_repair_does_not_create_or_reopen_poll(tmp_path, missing):
    async def scenario():
        bot = make_bot(tmp_path)
        if missing == "poll":
            bot.state["current_poll"] = None
        elif missing == "closed":
            bot.poll["is_open"] = False
        else:
            bot.poll["conversation_message_id"] = 0
        before = deepcopy(bot.state)
        await command(bot)
        assert not bot.api.edited
        assert bot.state == before
        assert "восстановлены" not in bot.api.sent[-1][1]
    asyncio.run(scenario())


@pytest.mark.parametrize("error", [VkApiError("messages.edit", {
    "error_code": 909, "error_msg": "Cannot edit message"}), httpx.ConnectError("Unavailable")])
def test_repair_reports_error_without_claiming_success(tmp_path, error):
    class FailingApi(FakeApi):
        async def edit_message(self, *args, **kwargs):
            raise error

    async def scenario():
        bot = make_bot(tmp_path, FailingApi())
        before = deepcopy(bot.state)
        await command(bot)
        assert bot.state == before
        assert "Не удалось восстановить" in bot.api.sent[-1][1]
        assert len(bot.api.sent) == 1
    asyncio.run(scenario())


def test_repair_is_repeatable_and_not_published_as_announcement(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path)
        bot.pending_announcements.add(10)
        before = deepcopy(bot.state)
        await command(bot, peer=10)
        await command(bot, peer=10)
        assert len(bot.api.edited) == 2
        assert bot.api.edited[0] == bot.api.edited[1]
        assert bot.state == before
        assert all(text != "/repair" for _, text, _ in bot.api.sent)
        assert 10 in bot.pending_announcements
    asyncio.run(scenario())

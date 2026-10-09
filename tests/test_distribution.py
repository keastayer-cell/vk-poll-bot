import asyncio

import pytest
from fakes import FakeApi, make_settings

from vk_poll_bot.api import SentMessage, VkApiError
from vk_poll_bot.models import new_poll_state
from vk_poll_bot.service import PollService
from vk_poll_bot.storage import JsonStateRepository


def make_bot(tmp_path, total=11, api=None):
    bot = PollService(api or FakeApi(), make_settings(tmp_path),
                      JsonStateRepository(tmp_path / "state.json"))
    bot.state["players"] = {
        str(i): {"name": f"Игрок {i}", "rating": 6 if i > 2 else None,
                 "position": "field" if i > 2 else "goalkeeper"}
        for i in range(1, total + 1)
    }
    poll = new_poll_state(bot.now().strftime("%Y-%m-%d"), "Идете?", bot.settings.peer_id)
    poll["voters"] = {key: {"name": p["name"], "choice": "yes"}
                      for key, p in bot.state["players"].items()}
    bot.state["current_poll"] = poll
    bot.save()
    return bot


async def message(bot, text, user=10, private=False):
    await bot.handle_message_event({"object": {"message": {
        "peer_id": user if private else bot.settings.peer_id, "from_id": user, "text": text,
    }}})


async def vote(bot, user, choice):
    bot.api.names[user] = f"Игрок {user}"
    await bot.handle_vote_event({"object": {
        "peer_id": bot.settings.peer_id, "user_id": user,
        "payload": {"command": "vote", "poll_date": bot.poll["poll_date"], "choice": choice},
    }})


def team_messages(api):
    return [text for _, text, _ in api.sent if text.startswith("⚽ КОМАНДА")]


def test_repeat_and_restart_do_not_duplicate_teams(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path)
        await message(bot, "/teams")
        original = bot.state["team_distribution"]
        restored = PollService(bot.api, bot.settings, bot.repository)
        await restored.restore_active_poll()
        await asyncio.gather(message(restored, "/teams"), message(restored, "/teams"))
        assert len(team_messages(bot.api)) == 1
        assert restored.state["team_distribution"] == original
        assert not bot.api.deleted
        assert bot.api.sent[-1][1] == "Команды уже распределены. Составы актуальны."
    asyncio.run(scenario())


def test_admin_can_explicitly_rebuild_teams(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path)
        await message(bot, "/teams")
        original = bot.state["team_distribution"]["message_id"]
        await message(bot, "/teams rebuild", user=99)
        assert not bot.api.deleted
        await message(bot, "/teams rebuild")
        assert bot.api.deleted == [(bot.settings.peer_id, original, 0)]
        assert len(team_messages(bot.api)) == 2
        assert any("запросил пересборку" in text for _, text, _ in bot.api.sent)
    asyncio.run(scenario())


@pytest.mark.parametrize("private", [False, True])
def test_rating_changes_only_for_participants_rebuild_teams(tmp_path, private):
    async def scenario():
        bot = make_bot(tmp_path)
        await message(bot, "/teams")
        original = bot.state["team_distribution"]["message_id"]
        await message(bot, "/rating Игрок 3 6", private=private)
        await message(bot, "/rating Другой Игрок 7", private=private)
        assert not bot.api.deleted
        await message(bot, "/rating Игрок 3 7,5", private=private)
        assert bot.api.deleted == [(bot.settings.peer_id, original, 0)]
        assert len(team_messages(bot.api)) == 2
        assert "Игрок 3" in bot.state["team_distribution"]["text"]
        assert any("Антон изменил рейтинг игрока Игрок 3" in text
                   for _, text, _ in bot.api.sent)
    asyncio.run(scenario())


def test_real_yes_cancellation_under_ten_and_return(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path, total=10)
        await message(bot, "/teams")
        await vote(bot, 3, "cancel")
        assert len(bot.api.deleted) == 1
        assert bot.state["team_distribution"] is None
        assert len(team_messages(bot.api)) == 1
        assert any("Игрок 3 отменил «ДА»" in text for _, text, _ in bot.api.sent)
        assert any("минимум 10" in text for _, text, _ in bot.api.sent)
        await message(bot, "/teams")
        assert len(team_messages(bot.api)) == 1
        await vote(bot, 3, "yes")
        assert len(team_messages(bot.api)) == 2
        assert bot.state["team_distribution"] is not None
    asyncio.run(scenario())


def test_no_votes_and_roster_button_do_not_invalidate_teams(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path)
        await message(bot, "/teams")
        await vote(bot, 99, "no")
        await vote(bot, 99, "cancel")
        await bot.handle_vote_event({"object": {
            "peer_id": bot.settings.peer_id, "user_id": 99,
            "payload": {"command": "toggle_roster", "poll_date": bot.poll["poll_date"]},
        }})
        assert not bot.api.deleted
        assert len(team_messages(bot.api)) == 1
    asyncio.run(scenario())


def test_guest_without_rating_clears_teams_and_setting_rating_rebuilds(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path, total=10)
        await message(bot, "/teams")
        await message(bot, "+1 Новый Гость")
        assert len(bot.api.deleted) == 1
        assert bot.state["team_distribution"] is None
        await message(bot, "/rating Новый Гость 6,5", private=True)
        assert len(team_messages(bot.api)) == 2
        await message(bot, "/minus1 Новый Гость")
        assert len(bot.api.deleted) == 2
        assert len(team_messages(bot.api)) == 3
        assert "Новый Гость" not in bot.state["team_distribution"]["text"]
    asyncio.run(scenario())


def test_role_change_invalidates_and_new_poll_removes_previous_teams(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path, total=10)
        await message(bot, "/teams")
        await message(bot, "/position Игрок 3 вратарь")
        assert len(bot.api.deleted) == 1
        assert bot.state["team_distribution"] is None
        await message(bot, "/position Игрок 3 полевой")
        await message(bot, "/rating Игрок 3 6")
        assert len(team_messages(bot.api)) == 2
        await bot.create_poll(force=True)
        assert len(bot.api.deleted) == 2
        assert bot.state["team_distribution"] is None
        assert not bot.poll.get("teams_requested")
    asyncio.run(scenario())


@pytest.mark.parametrize("edit_fails", [False, True])
def test_delete_failure_marks_stale_or_blocks_new_publication(tmp_path, edit_fails):
    class DeniedApi(FakeApi):
        async def delete_message(self, *args, **kwargs):
            raise VkApiError("messages.delete", {"error_code": 924})

        async def edit_message(self, *args, **kwargs):
            if edit_fails:
                raise VkApiError("messages.edit", {"error_code": 15})
            await super().edit_message(*args, **kwargs)

    async def scenario():
        bot = make_bot(tmp_path, api=DeniedApi())
        await message(bot, "/teams")
        await message(bot, "/rating Игрок 3 7")
        if edit_fails:
            assert len(team_messages(bot.api)) == 1
            assert bot.state["team_distribution"]["invalidated"]
            assert any("VK не разрешил" in text for _, text, _ in bot.api.sent)
            bot.api.delete_message = FakeApi.delete_message.__get__(bot.api)
            await message(bot, "/teams")
        else:
            assert "РАСПРЕДЕЛЕНИЕ НЕАКТУАЛЬНО" in bot.api.edited[-1][3]
        assert len(team_messages(bot.api)) == 2
        assert not bot.state["team_distribution"].get("invalidated")
    asyncio.run(scenario())


def test_late_outgoing_ids_finish_invalidated_message_cleanup(tmp_path):
    class LateIdsApi(FakeApi):
        async def send_message(self, peer_id, text, keyboard=None):
            sent = await super().send_message(peer_id, text, keyboard)
            if text.startswith("⚽ КОМАНДА"):
                return SentMessage(message_id=0, random_id=12345)
            return sent

    async def scenario():
        bot = make_bot(tmp_path, api=LateIdsApi())
        await message(bot, "/teams")
        text = bot.state["team_distribution"]["text"]
        await message(bot, "/rating Игрок 3 7")
        assert bot.state["team_distribution"]["invalidated"]
        assert len(team_messages(bot.api)) == 1
        await bot.handle_outgoing_message({"object": {"message": {
            "peer_id": bot.settings.peer_id, "id": 0, "conversation_message_id": 42,
            "random_id": 12345, "text": text,
        }}})
        assert bot.api.deleted == [(bot.settings.peer_id, 0, 42)]
        assert len(team_messages(bot.api)) == 2
    asyncio.run(scenario())


def test_lower_rating_scale_survives_restart_and_updates_starters(tmp_path):
    async def scenario():
        bot = make_bot(tmp_path)
        bot.state['rating_order'] = 'lower'
        for player in bot.state['players'].values():
            if player['position'] == 'field':
                player['rating'] = 2
        bot.save()
        restored = PollService(bot.api, bot.settings, bot.repository)
        assert restored.state['rating_order'] == 'lower'
        await message(restored, '/teams')
        assert restored.state['team_distribution']['snapshot']['rating_order'] == 'lower'
        await message(restored, '/rating Игрок 3 5')
        assert restored.state['players']['3']['rating'] == 2
        await message(restored, '/rating Игрок 3 1')
        assert restored.state['players']['3']['rating'] == 1
        text = restored.state['team_distribution']['text']
        section = next(part for part in text.split('⚽ КОМАНДА') if 'Игрок 3' in part)
        assert 'Игрок 3' in section.split('Замены\n')[0]
    asyncio.run(scenario())

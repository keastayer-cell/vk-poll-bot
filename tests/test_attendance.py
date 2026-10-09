import asyncio
from copy import deepcopy

from fakes import FakeApi, make_settings

from vk_poll_bot.attendance import record_closed_poll, statistics_text
from vk_poll_bot.models import new_poll_state, normalize_state
from vk_poll_bot.service import PollService
from vk_poll_bot.storage import JsonStateRepository


def test_real_yes_only_and_idempotent_after_restart():
    state = normalize_state({}, {})
    poll = new_poll_state("2026-10-09", "Идете?", 2000000001)
    poll["voters"] = {
        "20": {"name": "Антон Корытов", "choice": "yes"},
        "21": {"name": "Не идёт", "choice": "no"},
    }
    poll["manual_yes_voters"] = {"manual:1": {"label": "Антон Корытов"},
                                  "manual:2": {"label": "Петров"}}
    poll["is_open"] = False
    assert record_closed_poll(state, poll)
    assert state["attendance"]["players"] == {
        "20": {"name": "Антон Корытов", "yes_count": 1},
        "21": {"name": "Не идёт", "yes_count": 0, "no_count": 1},
    }
    restored = normalize_state(deepcopy(state), {})
    assert not record_closed_poll(restored, poll)
    assert restored == state
    second = new_poll_state("2026-10-09", "Идете?", 2000000001)
    second["voters"] = {"20": {"name": "Новое имя", "choice": "yes"}}
    second["is_open"] = False
    assert record_closed_poll(restored, second)
    assert restored["attendance"]["players"]["20"] == {"name": "Новое имя", "yes_count": 2}
    assert len(restored["attendance"]["players"]) == 2


def test_close_persists_counts_and_archive_with_no_repeat(tmp_path):
    async def scenario():
        api = FakeApi()
        settings = make_settings(tmp_path)
        repository = JsonStateRepository(tmp_path / "state.json")
        bot = PollService(api, settings, repository)
        await bot.create_poll("2026-10-09")
        poll_id = bot.poll["poll_id"]
        bot.poll["voters"] = {"20": {"name": "Антон", "choice": "yes"}}
        await bot.close_poll()
        await bot.close_poll()
        restored = PollService(api, settings, repository)
        assert restored.state["attendance"]["players"]["20"]["yes_count"] == 1
        assert restored.state["attendance"]["polls"][poll_id]["real_yes"] == {"20": "Антон"}
        assert restored.poll is None
        await restored.handle_message_event({"object": {"message": {
            "peer_id": settings.peer_id, "from_id": 20, "text": "/stats",
        }}})
        assert "1 │" in api.sent[-1][1] and "0 │ Антон" in api.sent[-1][1]

    asyncio.run(scenario())


def test_new_poll_archives_previous_open_poll(tmp_path):
    async def scenario():
        bot = PollService(FakeApi(), make_settings(tmp_path),
                          JsonStateRepository(tmp_path / "state.json"))
        await bot.create_poll("2026-10-09")
        bot.poll["voters"] = {"20": {"name": "Антон", "choice": "yes"}}
        await bot.create_poll("2026-10-10")
        assert bot.state["attendance"]["players"]["20"]["yes_count"] == 1
        assert bot.poll["poll_date"] == "2026-10-10"

    asyncio.run(scenario())


def test_display_uses_current_name_and_sorts_by_count():
    state = {"attendance": {"polls": {"p": {}}, "players": {
        "1": {"name": "Старое", "yes_count": 2}, "2": {"name": "Другой", "yes_count": 1},
    }}, "players": {"1": {"name": "Текущее имя"}}}
    result = statistics_text(state)
    assert "Старое" not in result
    assert result.index("Текущее имя") < result.index("Другой")


def test_close_counts_refusals_and_silent_members_once(tmp_path):
    async def scenario():
        api = FakeApi()
        api.names = {20: 'Идёт', 21: 'Отказался', 22: 'Промолчал', -1: 'Бот'}
        bot = PollService(api, make_settings(tmp_path),
                          JsonStateRepository(tmp_path / 'state.json'))
        await bot.create_poll('2026-10-09')
        bot.poll['voters'] = {
            '20': {'name': 'Идёт', 'choice': 'yes'},
            '21': {'name': 'Отказался', 'choice': 'no'},
        }
        bot.poll['manual_yes_voters'] = {'manual:1': {'label': 'Гость'}}
        assert not bot.state['attendance']['players']
        await bot.close_poll()
        await bot.close_poll()
        players = bot.state['attendance']['players']
        assert set(players) == {'20', '21', '22'}
        assert players['20']['yes_count'] == 1
        assert players['21']['no_count'] == 1
        assert players['22']['unanswered_count'] == 1
        assert '1 │ Промолчал' in statistics_text(bot.state)
        # A new member is not charged for past polls, and leaving stops future misses.
        api.names = {20: 'Идёт', 23: 'Новенький'}
        await bot.create_poll('2026-10-10')
        await bot.close_poll()
        assert players['22']['unanswered_count'] == 1
        assert players['23']['unanswered_count'] == 1
        assert players['20']['unanswered_count'] == 1
    asyncio.run(scenario())


def test_member_fetch_failure_leaves_poll_open_without_partial_statistics(tmp_path):
    class BrokenApi(FakeApi):
        async def conversation_members(self, peer_id):
            raise RuntimeError('VK unavailable')

    async def scenario():
        bot = PollService(BrokenApi(), make_settings(tmp_path),
                          JsonStateRepository(tmp_path / 'state.json'))
        await bot.create_poll('2026-10-09')
        await bot.close_poll()
        assert bot.poll['is_open']
        assert not bot.state['attendance']['polls']
        assert not await bot.create_poll('2026-10-10')
        assert bot.poll['poll_date'] == '2026-10-09'
    asyncio.run(scenario())

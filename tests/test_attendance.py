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
    assert record_closed_poll(state, poll)
    assert state["attendance"]["players"] == {"20": {"name": "Антон Корытов", "yes_count": 1}}
    restored = normalize_state(deepcopy(state), {})
    assert not record_closed_poll(restored, poll)
    assert restored == state
    second = new_poll_state("2026-10-09", "Идете?", 2000000001)
    second["voters"] = {"20": {"name": "Новое имя", "choice": "yes"}}
    assert record_closed_poll(restored, second)
    assert restored["attendance"]["players"]["20"] == {"name": "Новое имя", "yes_count": 2}
    assert len(restored["attendance"]["players"]) == 1


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
        assert "1 │ Антон" in api.sent[-1][1]

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

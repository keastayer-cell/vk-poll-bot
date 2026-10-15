import asyncio
from copy import deepcopy

import pytest
from fakes import FakeApi, make_settings

from vk_poll_bot.service import PollService
from vk_poll_bot.storage import JsonStateRepository
from vk_poll_bot.teams import find_player, link_guest_players, poll_players


def registry():
    return {"guest:петров": {"name": "Петров Николай", "rating": 2,
                             "position": "field", "aliases": ["Петров"]}}


@pytest.mark.parametrize("existing", [None, {"name": "Николай Петров", "rating": None},
                                     {"name": "Николай Петров", "rating": 2,
                                      "position": "field", "aliases": ["Коля Петров"]}])
def test_links_guest_without_losing_rating_aliases_or_existing_identity(existing):
    players = registry()
    if existing is not None:
        players["20"] = deepcopy(existing)
    assert link_guest_players(players, {"20": "Николай Петров"}) == ["20"]
    assert len(players) == 1
    assert players["20"]["rating"] == 2
    assert players["20"]["position"] == "field"
    for name in ("Петров", "Петров Николай", "Николай Петров"):
        assert find_player(players, name) == "20"
    if existing and existing.get("aliases"):
        assert find_player(players, "Коля Петров") == "20"
    assert link_guest_players(players, {"20": "Николай Петров"}) == []
    poll = {"voters": {"20": {"name": "Николай Петров", "choice": "yes"}},
            "manual_yes_voters": {"manual:1": {"label": "Петров"}}}
    with pytest.raises(ValueError, match="дважды"):
        poll_players(poll, players)


@pytest.mark.parametrize("case", ["member_namesakes", "registry_namesake", "guest_namesakes",
                                  "rating_conflict", "role_conflict", "surname_only",
                                  "alias_namesake"])
def test_ambiguous_or_conflicting_players_are_never_merged(case):
    players = registry()
    members = {"20": "Николай Петров"}
    if case == "member_namesakes":
        members["21"] = "Петров Николай"
    elif case == "registry_namesake":
        players["21"] = {"name": "Николай Петров", "rating": 3, "position": "field"}
    elif case == "guest_namesakes":
        players["guest:other"] = {"name": "Николай Петров", "rating": 3, "position": "field"}
    elif case == "rating_conflict":
        players["20"] = {"name": "Николай Петров", "rating": 3, "position": "field"}
    elif case == "role_conflict":
        players["20"] = {"name": "Николай Петров", "rating": None, "position": "goalkeeper"}
    elif case == "alias_namesake":
        players["guest:петров"]["aliases"].append("Александр Петров")
        members["21"] = "Александр Петров"
    else:
        players["guest:петров"]["name"] = "Петров"
    original = deepcopy(players)
    assert link_guest_players(players, members) == []
    assert players == original


@pytest.mark.parametrize("trigger", ["vote", "repeat_vote", "join", "join_link", "sync",
                                     "rating", "restore"])
def test_guest_becomes_member_and_current_poll_keeps_the_rating(tmp_path, trigger):
    async def scenario():
        api = FakeApi()
        api.names[20] = "Николай Петров"
        bot = PollService(api, make_settings(tmp_path),
                          JsonStateRepository(tmp_path / "state.json"))
        await bot.create_poll("2026-10-15")
        bot.state["players"] = registry()
        bot.poll["show_roster"] = True
        if trigger != "vote":
            bot.poll["voters"]["20"] = {"name": "Николай Петров", "choice": "yes"}
        bot.save()
        attendance = deepcopy(bot.state["attendance"])
        if trigger in {"vote", "repeat_vote"}:
            await bot.handle_vote_event({"object": {
                "peer_id": bot.settings.peer_id, "user_id": 20,
                "payload": {"command": "vote", "poll_date": bot.poll["poll_date"],
                            "choice": "yes"},
            }})
        elif trigger in {"join", "join_link"}:
            await bot.handle_message_event({"object": {"message": {
                "peer_id": bot.settings.peer_id, "from_id": 20, "text": "",
                "action": {"type": "chat_invite_user" if trigger == "join"
                           else "chat_invite_user_by_link", "member_id": 20},
            }}})
        elif trigger in {"sync", "rating"}:
            await bot.handle_message_event({"object": {"message": {
                "peer_id": 10, "from_id": 10,
                "text": "/players sync" if trigger == "sync" else "/rating Николай Петров 2",
            }}})
        else:
            await bot.restore_active_poll()
        assert "guest:петров" not in bot.state["players"]
        assert bot.state["players"]["20"]["rating"] == 2
        assert bot.poll["voters"]["20"] == {"name": "Николай Петров", "choice": "yes"}
        assert "Николай Петров │ 2" in api.edited[-1][3]
        assert bot.state["attendance"] == attendance
        restored = PollService(api, bot.settings, bot.repository)
        assert restored.state["players"]["20"]["rating"] == 2
        assert find_player(restored.state["players"], "Петров") == "20"
    asyncio.run(scenario())


def test_rating_namesake_does_not_claim_success_or_change_the_guest(tmp_path):
    async def scenario():
        api = FakeApi()
        api.names.update({20: "Николай Петров", 21: "Николай Петров"})
        bot = PollService(api, make_settings(tmp_path),
                          JsonStateRepository(tmp_path / "state.json"))
        bot.state["players"] = registry()
        original = deepcopy(bot.state["players"])
        await bot.handle_message_event({"object": {"message": {
            "peer_id": 10, "from_id": 10, "text": "/rating Николай Петров 3",
        }}})
        assert bot.state["players"] == original
        assert "Укажите VK ID" in api.sent[-1][1]
        assert "Сохранено" not in api.sent[-1][1]
    asyncio.run(scenario())


@pytest.mark.parametrize("query", ["Николай Петров", "Петров Николай", "20"])
def test_rating_unregistered_member_uses_vk_id_instead_of_creating_guest(tmp_path, query):
    async def scenario():
        api = FakeApi()
        api.names[20] = "Николай Петров"
        bot = PollService(api, make_settings(tmp_path),
                          JsonStateRepository(tmp_path / "state.json"))
        await bot.handle_message_event({"object": {"message": {
            "peer_id": 10, "from_id": 10, "text": f"/rating {query} 2",
        }}})
        assert list(bot.state["players"]) == ["20"]
        assert bot.state["players"]["20"]["rating"] == 2
        assert api.sent[-1][1] == "Сохранено: Николай Петров — 2"
    asyncio.run(scenario())

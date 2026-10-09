import asyncio

import pytest
from fakes import FakeApi, make_settings

from vk_poll_bot.api import VkApiError
from vk_poll_bot.models import new_poll_state
from vk_poll_bot.service import PollService
from vk_poll_bot.storage import JsonStateRepository
from vk_poll_bot.teams import (
    add_alias,
    balanced_five_four_four,
    balanced_teams,
    balanced_with_substitutes,
    find_player,
    poll_players,
    teams_text,
)
from vk_poll_bot.text_tables import player_row


def test_guest_aliases_share_identity_rating_and_detect_duplicate_votes():
    players = {"20": {"name": "Антон Корытов", "rating": 7, "position": "field"}}
    add_alias(players, "20", "Антон")
    add_alias(players, "Антон Корытов", "Корытов")
    add_alias(players, "20", "антон")
    assert players["20"]["aliases"] == ["Антон", "Корытов"]
    for label in ["Антон", "Корытов", "Корытов Антон"]:
        poll = {"manual_yes_voters": {"manual:1": {"label": label}}}
        assert poll_players(poll, players)[0]["id"] == "20"
        assert poll_players(poll, players)[0]["rating"] == 7
    poll["manual_yes_voters"]["manual:2"] = {"label": "Антон"}
    with pytest.raises(ValueError, match="дважды"):
        poll_players(poll, players)
    players["21"] = {"name": "Антон Петров", "aliases": ["Антоха"]}
    with pytest.raises(ValueError, match="другому игроку"):
        add_alias(players, "21", "Антон")
    with pytest.raises(ValueError, match="другому игроку"):
        add_alias(players, "20", "Антон Петров")


@pytest.mark.parametrize("size", [10, 15])
def test_balances_five_player_teams_without_duplicates(size):
    # Each rating occurs twice or three times: perfectly equal totals are possible.
    players = [{"id": str(i), "name": str(i), "rating": i % 5 + 1} for i in range(size)]
    teams = balanced_teams(players)
    assert len(teams) == size // 5
    assert all(len(team) == 5 for team in teams)
    assert sorted(p["id"] for team in teams for p in team) == sorted(p["id"] for p in players)
    assert {sum(p["rating"] for p in team) for team in teams} == {15}


@pytest.mark.parametrize("ratings,expected", [
    ([8, 8, 8, 1, 5, 5, 5, 5], [[8, 8, 5, 1], [8, 5, 5, 5]]),
    # Exactly equal totals would put all three stars plus the weakest player together.
    ([8, 8, 8, 1, 7, 6, 6, 6], [[8, 8, 7, 1], [8, 6, 6, 6]]),
])
def test_balances_player_profiles_as_well_as_totals(ratings, expected):
    players = [{"id": str(i), "name": str(i), "rating": r} for i, r in enumerate(ratings)]
    teams = balanced_teams(players, team_size=4)
    profiles = [sorted([p["rating"] for p in team], reverse=True) for team in teams]
    assert sorted(profiles) == sorted(expected)


def test_three_teams_share_stars_and_weak_players():
    ratings = [9, 9, 9, 3, 3, 3, 6, 6, 6, 6, 6, 6]
    players = [{"id": str(i), "name": str(i), "rating": r} for i, r in enumerate(ratings)]
    teams = balanced_teams(players, team_size=4)
    assert all(sorted(p["rating"] for p in team) == [3, 6, 6, 9] for team in teams)


@pytest.mark.parametrize("ratings", [
    [6, 7, 8, 6, 2, 9, 5, 8, 8, 6, 6, 8, 7],
    [5] * 13,
    [10] + [1] * 12,
])
def test_thirteen_field_players_five_is_stronger_without_duplicates(ratings):
    players = [{"id": str(i), "name": str(i), "rating": r} for i, r in enumerate(ratings)]
    teams = balanced_five_four_four(players)
    assert [len(t) for t in teams] == [5, 4, 4]
    assert sorted(p["id"] for t in teams for p in t) == sorted(p["id"] for p in players)
    totals = [sum(p["rating"] for p in team) for team in teams]
    assert totals[0] > max(totals[1:])
    assert totals[0] * 4 >= max(totals[1:]) * 5


def test_fifteen_players_with_two_goalkeepers_are_supported():
    directory = {str(i): {"name": f"Игрок {i}", "position": "field", "rating": 6}
                 for i in range(15)}
    for i in (13, 14):
        directory[str(i)].update(position="goalkeeper", rating=None)
    poll = {"voters": {key: {"name": p["name"], "choice": "yes"}
                       for key, p in directory.items()}}
    output = teams_text(poll, directory)
    assert "КОМАНДА 1 · 5 полевых" in output
    assert output.count("4 полевых") == 2
    assert "Сумма 30" in output
    assert output.count("Сумма 24") == 2
    assert "Игрок 13" in output.split("Вратари (распределите сами):")[1]


def test_guests_names_missing_ratings_and_duplicates():
    players = {"1": {"name": "Иван Иванов", "rating": 7, "position": "field"}}
    poll = new_poll_state("2026-10-08", "Идете?")
    poll["manual_yes_voters"] = {"manual:1": {"label": "Иванов Иван"}}
    assert poll_players(poll, players)[0]["id"] == "1"
    poll["voters"] = {"1": {"name": "Иван Иванов", "choice": "yes"}}
    with pytest.raises(ValueError, match="дважды"):
        poll_players(poll, players)
    poll["manual_yes_voters"] = {}
    players["1"]["rating"] = None
    with pytest.raises(ValueError, match="Не заполнен рейтинг"):
        poll_players(poll, players)
    players["2"] = {"name": "Иван Иванов", "rating": 8}
    with pytest.raises(ValueError, match="тёзки"):
        find_player(players, "Иван Иванов")


def test_imperfect_balance_and_output_shows_ratings():
    players = [{"id": str(i), "name": f"Игрок {i}", "rating": 10 if i == 0 else 1}
               for i in range(15)]
    teams = balanced_teams(players)
    assert sorted(sum(p["rating"] for p in team) for team in teams) == [5, 5, 14]
    directory = {p["id"]: p for p in players}
    for i, p in enumerate(players):
        p["position"] = "goalkeeper" if i >= 12 else "field"
        if i >= 12:
            p["rating"] = None
    poll = {"voters": {p["id"]: {"name": p["name"], "choice": "yes"} for p in players}}
    output = teams_text(poll, directory)
    assert "КОМАНДА 3" in output
    assert player_row({"name": "Игрок 0", "rating": 10}) in output
    assert "Сумма" in output
    assert "Вратари (распределите сами):" in output


@pytest.mark.parametrize("total", [10, 15])
def test_goalkeepers_excluded_and_positions_required(total):
    directory = {str(i): {"name": f"Игрок {i}", "position": "field", "rating": 5}
                 for i in range(total)}
    for i in range(total - total // 5, total):
        directory[str(i)].update(position="goalkeeper", rating=None)
    poll = {"voters": {key: {"name": p["name"], "choice": "yes"}
                       for key, p in directory.items()}}
    output = teams_text(poll, directory)
    fields, keepers = output.split("Вратари (распределите сами):")
    for i in range(total - total // 5, total):
        assert f"Игрок {i}\n" not in fields
        assert f"Игрок {i}" in keepers
    directory["0"].pop("position")
    with pytest.raises(ValueError, match="Не задана роль"):
        teams_text(poll, directory)
    directory["0"].update(position="goalkeeper", rating=None)
    assert "Проверьте роли" in teams_text(poll, directory)


@pytest.mark.parametrize("size", [9, 16])
def test_unresolved_player_counts(size):
    poll = {"voters": {str(i): {"name": str(i), "choice": "yes"} for i in range(size)}}
    assert f"Записалось {size}" in teams_text(poll, {})


@pytest.mark.parametrize("total,keepers,sizes", [
    (10, 2, [4, 4]), (11, 2, [5, 4]), (12, 2, [5, 5]),
    (13, 2, [6, 5]), (14, 2, [4, 4, 4]), (15, 2, [5, 4, 4]),
    (11, 3, [4, 4]), (12, 3, [5, 4]), (13, 3, [5, 5]),
    (14, 3, [6, 5]), (15, 3, [4, 4, 4]),
])
def test_squad_sizes_follow_field_count_and_show_substitutes(total, keepers, sizes):
    directory = {str(i): {"name": f"Игрок {i}", "position": "field", "rating": 6}
                 for i in range(total)}
    for i in range(total - keepers, total):
        directory[str(i)].update(position="goalkeeper", rating=None)
    poll = {"voters": {key: {"name": p["name"], "choice": "yes"}
                       for key, p in directory.items()}}
    output = teams_text(poll, directory)
    assert output.count("⚽ КОМАНДА") == len(sizes)
    for number, size in enumerate(sizes, 1):
        assert f"КОМАНДА {number} · {size} полевых\nНа поле: 4 · Замены: {size - 4}" in output
    fields, keeper_text = output.split("🧤 Вратари")
    for i in range(total):
        assert (fields if i < total - keepers else keeper_text).count(f"│ Игрок {i}\n") == 1 \
            or (fields if i < total - keepers else keeper_text).endswith(f"│ Игрок {i}")


@pytest.mark.parametrize("ratings", [
    [8, 8, 8, 1, 5, 5, 5, 5, 5],
    [10] + [1] * 8,
    [7.5, 3, 5, 6.5, 8, 2, 7, 4, 9, 6, 5.5],
    [6] * 11,
])
def test_unequal_squads_keep_every_player_and_larger_squad_stronger(ratings):
    players = [{"id": str(i), "rating": r} for i, r in enumerate(ratings)]
    teams = balanced_with_substitutes(players)
    assert [len(t) for t in teams] == [(len(players) + 1) // 2, len(players) // 2]
    assert sorted(p["id"] for t in teams for p in t) == sorted(p["id"] for p in players)
    totals = [sum(p["rating"] for p in t) for t in teams]
    assert totals[0] > totals[1]
    assert totals[0] * len(teams[1]) >= totals[1] * len(teams[0])


def test_admin_private_ratings_persist_and_sync_preserves_them(tmp_path):
    async def scenario():
        api = FakeApi()

        async def members(peer_id):
            return {"20": "Иван Иванов", "21": "Пётр Петров"}

        api.conversation_members = members
        settings = make_settings(tmp_path)
        repository = JsonStateRepository(tmp_path / "state.json")
        bot = PollService(api, settings, repository)

        async def message(text, sender=10, peer=10):
            await bot.handle_message_event({"object": {"message": {
                "peer_id": peer, "from_id": sender, "text": text,
            }}})

        await message("/players sync")
        await message("/rating 20 8")
        await message("/alias 20 | Ваня")
        await message("/rating Ваня 8")
        assert len(bot.state["players"]) == 2
        await message("/players sync")
        assert bot.state["players"]["20"]["rating"] == 8
        assert bot.state["players"]["20"]["aliases"] == ["Ваня"]
        await message("/rating Приглашённый Игрок 6")
        await message("/rating 20 11")
        assert bot.state["players"]["20"]["rating"] == 8
        await message("/rating 20 1", sender=21, peer=21)
        await message("/rating 20 8", peer=settings.peer_id)
        assert bot.state["players"]["20"]["rating"] == 8
        await message("/position 21 вратарь")
        await message("/rating 21 9")
        assert bot.state["players"]["21"]["rating"] is None
        assert bot.state["players"]["21"]["position"] == "goalkeeper"
        await message("/players sync")
        assert bot.state["players"]["21"]["position"] == "goalkeeper"
        await message("/players")
        assert player_row({"name": "Иван Иванов", "rating": 8}) in api.sent[-1][1]
        assert "🧤 │ Пётр Петров" in api.sent[-1][1]
        assert "guest:" not in api.sent[-1][1]
        assert "другие имена" not in api.sent[-1][1]

        assert any("Сохранено: Иван Иванов" in text for peer, text, _ in api.sent
                   if peer == settings.peer_id)
        restored = PollService(api, settings, repository)
        assert restored.state["players"] == bot.state["players"]
        await restored.create_poll("2026-10-08")
        await restored.close_poll()
        assert restored.state["players"] == bot.state["players"]

    asyncio.run(scenario())


@pytest.mark.parametrize("private", [True, False])
def test_anyone_can_read_ratings_but_even_other_admins_cannot_change_them(tmp_path, private):
    async def scenario():
        api = FakeApi()
        bot = PollService(api, make_settings(tmp_path, admin_ids=(10, 21)),
                          JsonStateRepository(tmp_path / "state.json"))
        bot.state["players"] = {"20": {"name": "Иван Иванов", "rating": 7, "position": "field"}}
        assert bot.is_admin(21)
        assert not bot.can_edit_ratings(21)

        async def message(text, sender):
            await bot.handle_message_event({"object": {"message": {
                "peer_id": sender if private else bot.settings.peer_id,
                "from_id": sender, "text": text,
            }}})

        await message("/players", 21)
        assert any(peer == 21 and player_row(bot.state["players"]["20"]) in text
                   for peer, text, _ in api.sent)
        if not private:
            assert api.sent[-1][1] == "Рейтинг отправлен в личные сообщения."
            assert all("Иван Иванов" not in text for peer, text, _ in api.sent
                       if peer == bot.settings.peer_id)
        for command in ("/rating 20 1", "/position 20 вратарь",
                        "/alias 20 | Ваня", "/players sync"):
            await message(command, 21)
            assert "только владелец рейтинга" in api.sent[-1][1]
        assert bot.state["players"]["20"] == {
            "name": "Иван Иванов", "rating": 7, "position": "field",
        }
        await message("/rating 20 6,5", 10)
        assert bot.state["players"]["20"]["rating"] == 6.5
        await message("/alias 20 | Ваня", 10)
        assert bot.state["players"]["20"]["aliases"] == ["Ваня"]
        await message("/position 20 вратарь", 10)
        assert bot.state["players"]["20"]["position"] == "goalkeeper"
        before = len(api.sent)
        await bot.handle_message_event({"object": {"message": {
            "peer_id": 2000000099, "from_id": 10, "text": "/rating 20 1",
        }}})
        assert len(api.sent) == before
    asyncio.run(scenario())


def test_rating_owner_stays_anton_with_older_production_settings(tmp_path):
    async def scenario():
        settings = make_settings(tmp_path, admin_ids=(550539899, 23772422, 11288242))
        del settings.rating_owner_id
        bot = PollService(FakeApi(), settings, JsonStateRepository(tmp_path / "state.json"))
        assert bot.can_edit_ratings(550539899)
        for user in (23772422, 11288242):
            assert bot.is_admin(user)
            assert not bot.can_edit_ratings(user)
    asyncio.run(scenario())


@pytest.mark.parametrize("code", [901, 902, 6])
def test_chat_rating_delivery_failure_does_not_publish_list(tmp_path, code):
    class BlockedPrivateApi(FakeApi):
        async def send_message(self, peer_id, text, keyboard=None):
            if peer_id == 21:
                raise VkApiError("messages.send", {"error_code": code})
            return await super().send_message(peer_id, text, keyboard)

    async def scenario():
        api = BlockedPrivateApi()
        bot = PollService(api, make_settings(tmp_path),
                          JsonStateRepository(tmp_path / "state.json"))
        bot.state["players"] = {"20": {"name": "Иван Иванов", "rating": 7, "position": "field"}}
        await bot.handle_message_event({"object": {"message": {
            "peer_id": bot.settings.peer_id, "from_id": 21, "text": "/players",
        }}})
        assert len(api.sent) == 1
        text = api.sent[0][1]
        assert "Иван Иванов" not in text
        assert "Рейтинг отправлен" not in text
        if code in {901, 902}:
            assert "https://vk.me/club241716551" in text
            assert "напишите /players" in text
        else:
            assert "Попробуйте позже" in text
    asyncio.run(scenario())

import json

import pytest

from vk_poll_bot.storage import JsonStateRepository, import_player_registry


def test_import_is_once_and_preserves_production_state(tmp_path):
    repository = JsonStateRepository(tmp_path / "state.json")
    original = {"current_poll": {"poll_id": "production"}, "schedule": {"poll_hour": 8},
                "attendance": {"players": {}, "polls": {}}}
    repository.save(original)
    source = tmp_path / "players.json"
    players = {"20": {"name": "Игрок", "rating": 6.5, "position": "field"},
               "guest:кипер": {"name": "Кипер", "rating": None, "position": "goalkeeper"}}
    source.write_text(json.dumps(players))
    assert import_player_registry(repository, source) == 2
    assert repository.load() == {**original, "players": players}
    assert json.loads(repository.backup_path.read_text()) == original
    assert not source.exists()
    assert json.loads((tmp_path / "players.json.imported").read_text()) == players
    state = repository.load()
    state["players"]["20"]["rating"] = 7
    repository.save(state)
    assert import_player_registry(repository, source) == 0
    assert repository.load()["players"]["20"]["rating"] == 7


def test_existing_ratings_are_never_overwritten(tmp_path):
    repository = JsonStateRepository(tmp_path / "state.json")
    repository.save({"players": {"20": {"rating": 7}}})
    source = tmp_path / "players.json"
    source.write_text('{}')
    assert import_player_registry(repository, source) == 0
    assert repository.load()["players"]["20"]["rating"] == 7


def test_invalid_import_leaves_state_and_source_unchanged(tmp_path):
    repository = JsonStateRepository(tmp_path / "state.json")
    original = {"current_poll": None, "schedule": {"poll_hour": 8}}
    repository.save(original)
    source = tmp_path / "players.json"
    source.write_text(json.dumps({"20": {"name": "Игрок", "position": "field", "rating": 100}}))
    with pytest.raises(ValueError):
        import_player_registry(repository, source)
    assert repository.load() == original
    assert source.exists()

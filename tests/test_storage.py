from vk_poll_bot.storage import JsonStateRepository


def test_state_round_trip(tmp_path) -> None:
    repository = JsonStateRepository(tmp_path / "state.json")
    state = {"schema_version": 1, "current_poll": {"is_open": True}}

    repository.save(state)

    assert repository.load() == state
    assert (tmp_path / "state.json").stat().st_mode & 0o777 == 0o600


def test_history_upgrade_keeps_original_state_backup_without_overwriting_it(tmp_path):
    import hashlib
    import json

    repository = JsonStateRepository(tmp_path / "state.json")
    original = {"schema_version": 1, "current_poll": None,
                "players": {"fixture": {"name": "Вымышленный", "rating": 2}},
                "attendance": {"players": {}, "polls": {}}}
    repository.save(original)
    original_bytes = repository.path.read_bytes()
    repository.save({**original, "team_history": []})
    assert repository.history_backup_path.read_bytes() == original_bytes
    assert hashlib.sha256(repository.history_backup_path.read_bytes()).digest() == hashlib.sha256(
        original_bytes).digest()
    assert repository.history_backup_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(repository.history_backup_path.read_bytes()) == original
    repository.save({**original, "team_history": [], "rating_order": "lower"})
    assert repository.history_backup_path.read_bytes() == original_bytes
    assert repository.load()["players"] == original["players"]

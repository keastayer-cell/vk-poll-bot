from vk_poll_bot.storage import JsonStateRepository


def test_state_round_trip(tmp_path) -> None:
    repository = JsonStateRepository(tmp_path / "state.json")
    state = {"schema_version": 1, "current_poll": {"is_open": True}}

    repository.save(state)

    assert repository.load() == state
    assert (tmp_path / "state.json").stat().st_mode & 0o777 == 0o600

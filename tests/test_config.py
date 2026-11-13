from vk_poll_bot.config import load_settings


def test_default_schedule_is_monday_and_thursday(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("VK_GROUP_TOKEN", "secret")
    monkeypatch.setenv("VK_GROUP_ID", "241716551")
    monkeypatch.setenv("VK_PEER_ID", "0")
    monkeypatch.delenv("POLL_DAYS", raising=False)
    monkeypatch.delenv("POLL_TIME", raising=False)

    settings = load_settings(tmp_path)

    assert settings.poll_days == "mon,thu"
    assert (settings.poll_hour, settings.poll_minute) == (8, 0)
    assert (settings.remind_mon_hour, settings.remind_mon_minute) == (19, 45)
    assert (settings.remind_thu_hour, settings.remind_thu_minute) == (18, 15)
    assert settings.peer_id == 0


def configure_env(monkeypatch):
    monkeypatch.setenv("VK_GROUP_TOKEN", "SYNTHETIC_TEST_TOKEN")
    monkeypatch.setenv("VK_GROUP_ID", "241716551")
    # Also undo environment values written directly by load_dotenv in file-based tests.
    monkeypatch.setenv("RATING_OWNER_ID", "")
    monkeypatch.delenv("RATING_OWNER_ID")
    monkeypatch.delenv("ADMIN_IDS", raising=False)


def test_rating_owner_default_preserves_existing_access(monkeypatch, tmp_path):
    from vk_poll_bot.config import DEFAULT_RATING_OWNER_ID

    configure_env(monkeypatch)
    assert load_settings(tmp_path).rating_owner_id == DEFAULT_RATING_OWNER_ID


def test_rating_owner_is_loaded_from_env_file(tmp_path, monkeypatch):
    configure_env(monkeypatch)
    (tmp_path / ".env").write_text("RATING_OWNER_ID=123456\n", encoding="utf-8")
    assert load_settings(tmp_path).rating_owner_id == 123456


def test_explicit_environment_owner_takes_precedence_over_dotenv(tmp_path, monkeypatch):
    configure_env(monkeypatch)
    (tmp_path / ".env").write_text("RATING_OWNER_ID=123456\n", encoding="utf-8")
    monkeypatch.setenv("RATING_OWNER_ID", "987654")
    assert load_settings(tmp_path).rating_owner_id == 987654


def test_empty_admins_warn_without_blocking_initial_setup(monkeypatch, tmp_path, caplog):
    configure_env(monkeypatch)
    monkeypatch.setenv("ADMIN_IDS", "  ")
    settings = load_settings(tmp_path)
    assert settings.admin_ids == ()
    assert "ADMIN_IDS пуст" in caplog.text
    assert "/where" in caplog.text


def test_configured_admins_do_not_warn(monkeypatch, tmp_path, caplog):
    configure_env(monkeypatch)
    monkeypatch.setenv("ADMIN_IDS", "123, 456")
    assert load_settings(tmp_path).admin_ids == (123, 456)
    assert "ADMIN_IDS пуст" not in caplog.text


def test_invalid_rating_owner_is_rejected(monkeypatch, tmp_path):
    import pytest

    configure_env(monkeypatch)
    for value in ("", "0", "-1", "not-a-number", "1.5"):
        monkeypatch.setenv("RATING_OWNER_ID", value)
        with pytest.raises(ValueError, match="RATING_OWNER_ID"):
            load_settings(tmp_path)

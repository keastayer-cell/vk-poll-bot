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
    assert settings.peer_id == 0

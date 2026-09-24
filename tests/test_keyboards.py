import json

from vk_poll_bot.keyboards import decode_payload, poll_keyboard


def test_poll_keyboard_contains_two_callback_buttons() -> None:
    keyboard = json.loads(poll_keyboard("2026-09-24"))

    assert keyboard["inline"] is True
    assert [button["action"]["label"] for button in keyboard["buttons"][0]] == [
        "✅ ИДУ",
        "❌ НЕ ИДУ",
    ]
    assert decode_payload(keyboard["buttons"][0][0]["action"]["payload"])["choice"] == "yes"


def test_disabled_keyboard_has_no_buttons() -> None:
    assert json.loads(poll_keyboard("2026-09-24", disabled=True))["buttons"] == []

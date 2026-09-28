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
    assert keyboard["buttons"][1][0]["action"]["label"] == "↩ ОТМЕНИТЬ ГОЛОС"
    assert decode_payload(keyboard["buttons"][1][0]["action"]["payload"])["choice"] == "cancel"
    assert keyboard["buttons"][2][0]["action"]["label"] == "👥 ПОКАЗАТЬ СОСТАВ"
    assert (
        decode_payload(keyboard["buttons"][2][0]["action"]["payload"])["command"] == "toggle_roster"
    )


def test_poll_keyboard_can_hide_expanded_roster() -> None:
    keyboard = json.loads(poll_keyboard("2026-09-24", show_roster=True))

    assert keyboard["buttons"][2][0]["action"]["label"] == "🙈 СКРЫТЬ СОСТАВ"


def test_disabled_keyboard_has_no_buttons() -> None:
    assert json.loads(poll_keyboard("2026-09-24", disabled=True))["buttons"] == []

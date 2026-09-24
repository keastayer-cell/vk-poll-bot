import json


def poll_keyboard(poll_date: str, *, disabled: bool = False) -> str:
    if disabled:
        return json.dumps({"inline": True, "buttons": []}, ensure_ascii=False)
    buttons = []
    for label, choice, color in (
        ("✅ ИДУ", "yes", "positive"),
        ("❌ НЕ ИДУ", "no", "negative"),
    ):
        payload = json.dumps(
            {"command": "vote", "choice": choice, "poll_date": poll_date},
            ensure_ascii=False,
        )
        buttons.append(
            {
                "action": {"type": "callback", "label": label, "payload": payload},
                "color": color,
            }
        )
    return json.dumps({"inline": True, "buttons": [buttons]}, ensure_ascii=False)


def decode_payload(payload) -> dict:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}

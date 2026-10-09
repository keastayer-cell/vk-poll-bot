from __future__ import annotations


def record_closed_poll(state: dict, poll: dict) -> bool:
    attendance = state.setdefault("attendance", {"players": {}, "polls": {}})
    poll_id = poll["poll_id"]
    if poll_id in attendance["polls"]:
        return False
    real_yes = {
        key: voter["name"] for key, voter in poll.get("voters", {}).items()
        if key.isdigit() and int(key) > 0 and voter.get("choice") == "yes"
    }
    attendance["polls"][poll_id] = {
        "poll_date": poll["poll_date"], "peer_id": poll.get("peer_id", 0),
        "real_yes": real_yes,
    }
    for key, name in real_yes.items():
        entry = attendance["players"].setdefault(key, {"name": name, "yes_count": 0})
        entry["name"] = name
        entry["yes_count"] += 1
    return True


def statistics_text(state: dict) -> str:
    attendance = state.get("attendance", {"players": {}, "polls": {}})
    if not attendance["polls"]:
        return "Статистика пока пустая. Она появится после закрытия опроса."
    rows = []
    for key, entry in attendance["players"].items():
        name = state.get("players", {}).get(key, {}).get("name") or entry["name"]
        rows.append((entry["yes_count"], name))
    rows.sort(key=lambda row: (-row[0], row[1].casefold()))
    width = max((len(str(count)) for count, _ in rows), default=1)
    lines = ["📊 СТАТИСТИКА «ДА»", f"Закрытых опросов: {len(attendance['polls'])}", "",
             "ДА │ ФИО", "────────────────────"]
    lines += ["\u2007" * (width - len(str(count))) + f"{count} │ {name}"
              for count, name in rows]
    if not rows:
        lines.append("Реальных голосов «ДА» пока нет.")
    return "\n".join(lines)

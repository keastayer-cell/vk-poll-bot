from __future__ import annotations


def poll_counts_for_attendance(state: dict, poll: dict) -> bool:
    start_date = state.get("attendance", {}).get("start_date")
    return not start_date or poll.get("poll_date", "") >= start_date


def record_closed_poll(state: dict, poll: dict, members: dict | None = None) -> bool:
    if poll.get("is_open"):
        raise ValueError("Статистика считается только после закрытия опроса")
    if not poll_counts_for_attendance(state, poll):
        return False
    attendance = state.setdefault("attendance", {"players": {}, "polls": {}})
    poll_id = poll["poll_id"]
    if poll_id in attendance["polls"]:
        return False
    real_yes = {
        key: voter["name"] for key, voter in poll.get("voters", {}).items()
        if key.isdigit() and int(key) > 0 and voter.get("choice") == "yes"
    }
    real_no = {
        key: voter["name"] for key, voter in poll.get("voters", {}).items()
        if key.isdigit() and int(key) > 0 and voter.get("choice") == "no"
    }
    unanswered = {
        key: name for key, name in (members or {}).items()
        if key.isdigit() and int(key) > 0 and key not in real_yes and key not in real_no
    }
    attendance["polls"][poll_id] = {
        "poll_date": poll["poll_date"], "peer_id": poll.get("peer_id", 0),
        "real_yes": real_yes,
        "real_no": real_no, "unanswered": unanswered,
        "members_recorded": members is not None,
    }
    for entries, counter in (
        (real_yes, "yes_count"), (real_no, "no_count"), (unanswered, "unanswered_count")
    ):
        for key, name in entries.items():
            entry = attendance["players"].setdefault(key, {"name": name, "yes_count": 0})
            entry["name"] = name
            entry[counter] = entry.get(counter, 0) + 1
    return True


def statistics_text(state: dict) -> str:
    attendance = state.get("attendance", {"players": {}, "polls": {}})
    start_date = attendance.get("start_date")
    start_text = ".".join(reversed(start_date.split("-"))) if start_date else ""
    if not attendance["polls"]:
        if start_date:
            return (
                f"Статистика пока пустая. Учитываем опросы с {start_text}, "
                "только после закрытия. Более ранние тестовые опросы не учитываются."
            )
        return "Статистика пока пустая. Она появится после закрытия опроса."
    rows = []
    for key, entry in attendance["players"].items():
        name = state.get("players", {}).get(key, {}).get("name") or entry["name"]
        rows.append((entry.get("yes_count", 0),
                     entry.get("no_count", 0) + entry.get("unanswered_count", 0), name))
    rows.sort(key=lambda row: (-row[0], row[2].casefold()))
    widths = [max([len(title), *(len(str(row[i])) for row in rows)])
              for i, title in enumerate(("ДА", "НЕТ"))]
    lines = ["📊 СТАТИСТИКА ТРЕНИРОВОК", f"Закрытых опросов: {len(attendance['polls'])}", "",
             "ДА │ НЕТ │ ФИО", "────────────────────"]
    if start_date:
        lines.insert(1, f"Учёт с {start_text}")
    lines += [" │ ".join(
        "\u2007" * (widths[i] - len(str(row[i]))) + str(row[i]) for i in range(2)
    ) + f" │ {row[2]}" for row in rows]
    if not rows:
        lines.append("Участников пока нет.")
    lines += ["", "НЕТ = ответ «НЕТ» + не ответил на опрос.",
              "Считаем только после закрытия; приглашённые не учитываются."]
    if any(not poll.get("members_recorded") for poll in attendance["polls"].values()):
        lines.append("В старых опросах сохранены только «ДА»; пропуски не восстановлены.")
    return "\n".join(lines)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Choice = Literal["yes", "no"]
INVISIBLE_CHARACTERS = str.maketrans(
    {"\u200b": None, "\u200c": None, "\u200d": None, "\ufeff": None}
)


@dataclass(frozen=True)
class Counts:
    yes: int
    no: int
    manual_yes: int

    @property
    def total_yes(self) -> int:
        return self.yes + self.manual_yes


@dataclass(frozen=True)
class Notification:
    audience: Literal["chat", "admins"]
    text: str


def set_vote(state: dict, user_id: int, name: str, choice: Choice) -> str | None:
    key = str(user_id)
    previous = state.setdefault("voters", {}).get(key)
    state["voters"][key] = {"name": name, "choice": choice}
    if previous and previous.get("choice") == "yes" and choice != "yes":
        state["last_removed_yes_label"] = previous.get("name") or name
    return previous.get("choice") if previous else None


def remove_vote(state: dict, user_id: int) -> dict | None:
    previous = state.setdefault("voters", {}).pop(str(user_id), None)
    if previous and previous.get("choice") == "yes":
        state["last_removed_yes_label"] = previous.get("name") or f"id{user_id}"
    return previous


def counts(state: dict) -> Counts:
    voters = state.get("voters", {}).values()
    return Counts(
        yes=sum(voter.get("choice") == "yes" for voter in voters),
        no=sum(voter.get("choice") == "no" for voter in voters),
        manual_yes=len(state.get("manual_yes_voters", {})),
    )


def parse_plus_one(text: str, author_name: str) -> str | None:
    normalized = text.translate(INVISIBLE_CHARACTERS).strip()
    if normalized == "+1":
        return f"Гость от {author_name}"
    if not normalized.startswith("+1"):
        return None
    name = " ".join(normalized[2:].split())
    if not name or not name[0].isalpha():
        return None
    return name


def add_manual_vote(state: dict, label: str, user_id: int, user_name: str, now: datetime) -> str:
    sequence = int(state.get("manual_yes_seq", 0)) + 1
    state["manual_yes_seq"] = sequence
    key = f"manual:{sequence}"
    state.setdefault("manual_yes_voters", {})[key] = {
        "label": label,
        "added_by_user_id": user_id,
        "added_by_name": user_name,
        "added_at": now.isoformat(),
    }
    return key


def remove_manual_vote(state: dict, query: str = "") -> dict | None:
    votes = state.get("manual_yes_voters", {})
    if not votes:
        return None
    key = None
    if query.strip():
        normalized = " ".join(query.split()).casefold()
        for candidate in reversed(votes):
            if (
                candidate.casefold() == normalized
                or votes[candidate]["label"].casefold() == normalized
            ):
                key = candidate
                break
    else:
        key = next(reversed(votes))
    if key is None:
        return None
    removed = votes.pop(key)
    state["last_removed_yes_label"] = removed["label"]
    return removed


def evaluate_threshold(state: dict, threshold: int) -> list[Notification]:
    total = counts(state).total_yes
    previous = int(state.get("last_total_yes_count", total))
    events: list[Notification] = []
    if total < previous and state.get("notified_yes", False):
        label = state.get("last_removed_yes_label") or "Кто-то"
        if total < threshold:
            state["notified_yes"] = False
            state["notified_almost"] = total >= threshold - 1
            events.append(
                Notification(
                    "chat", f"{label} слился. Нас снова не хватает: {total} из {threshold}."
                )
            )
        else:
            events.append(
                Notification("chat", f"{label} слился. Осталось {total} «ДА», нас пока хватает.")
            )
    if (
        total == threshold - 1
        and not state.get("notified_almost")
        and not state.get("notified_yes")
    ):
        state["notified_almost"] = True
        events.append(Notification("chat", "Братики, еще 1 и идем 💪"))
    if total >= threshold and not state.get("notified_yes"):
        state["notified_yes"] = True
        events.extend(
            [
                Notification("chat", "Ну все, епта, идем играть, готовьтесь 🔥"),
                Notification("admins", f"✅ Набрано {threshold} «ДА»! Все идут."),
            ]
        )
    state["last_total_yes_count"] = total
    state["last_removed_yes_label"] = None
    return events


def format_status(state: dict, threshold: int, detailed: bool = False) -> str:
    result = counts(state)
    header = (
        f"«ДА»: {result.yes} + {result.manual_yes} вручную = "
        f"{result.total_yes} / {threshold}\n«Нет»: {result.no}"
    )
    if not detailed:
        return header
    yes_names = [v["name"] for v in state.get("voters", {}).values() if v["choice"] == "yes"]
    guest_names = [v["label"] for v in state.get("manual_yes_voters", {}).values()]
    sections = []
    for title, names in (("Реальные «ДА»", yes_names), ("Виртуальные +1", guest_names)):
        if names:
            sections.append(
                title + ":\n" + "\n".join(f"{i}. {name}" for i, name in enumerate(names, 1))
            )
    return header + ("\n\n" + "\n\n".join(sections) if sections else "")

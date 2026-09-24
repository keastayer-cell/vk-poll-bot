from __future__ import annotations

from typing import Any, TypedDict


class Voter(TypedDict):
    name: str
    choice: str


class ManualVote(TypedDict):
    label: str
    added_by_user_id: int
    added_by_name: str
    added_at: str


class PollState(TypedDict, total=False):
    poll_date: str
    question: str
    is_open: bool
    peer_id: int
    message_id: int
    conversation_message_id: int
    random_id: int
    voters: dict[str, Voter]
    manual_yes_voters: dict[str, ManualVote]
    manual_yes_seq: int
    last_total_yes_count: int
    last_removed_yes_label: str | None
    notified_almost: bool
    notified_yes: bool
    notified_deadline: bool
    sent_reminders: list[str]


def new_poll_state(poll_date: str, question: str, peer_id: int = 0) -> PollState:
    return {
        "poll_date": poll_date,
        "question": question,
        "is_open": True,
        "peer_id": peer_id,
        "message_id": 0,
        "conversation_message_id": 0,
        "random_id": 0,
        "voters": {},
        "manual_yes_voters": {},
        "manual_yes_seq": 0,
        "last_total_yes_count": 0,
        "last_removed_yes_label": None,
        "notified_almost": False,
        "notified_yes": False,
        "notified_deadline": False,
        "sent_reminders": [],
    }


def normalize_state(data: Any, default_schedule: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Корень state.json должен быть объектом")
    result = {
        "schema_version": 1,
        "current_poll": data.get("current_poll"),
        "schedule": {**default_schedule, **data.get("schedule", {})},
    }
    poll = result["current_poll"]
    if poll is not None:
        if not isinstance(poll, dict):
            raise ValueError("current_poll должен быть объектом или null")
        defaults = new_poll_state(
            str(poll.get("poll_date", "")),
            str(poll.get("question", "Идете?")),
            int(poll.get("peer_id", 0)),
        )
        defaults.update(poll)
        defaults["voters"] = dict(defaults.get("voters", {}))
        defaults["manual_yes_voters"] = dict(defaults.get("manual_yes_voters", {}))
        defaults["sent_reminders"] = list(defaults.get("sent_reminders", []))
        result["current_poll"] = defaults
    return result

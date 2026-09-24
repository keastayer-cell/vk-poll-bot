from typing import TypedDict


class Voter(TypedDict):
    name: str
    choice: str


class PollState(TypedDict):
    poll_date: str
    question: str
    is_open: bool
    voters: dict[str, Voter]
    manual_yes_voters: dict[str, str]
    last_total_yes_count: int
    notified_almost: bool
    notified_yes: bool


def new_poll_state(poll_date: str, question: str) -> PollState:
    return {
        "poll_date": poll_date,
        "question": question,
        "is_open": True,
        "voters": {},
        "manual_yes_voters": {},
        "last_total_yes_count": 0,
        "notified_almost": False,
        "notified_yes": False,
    }


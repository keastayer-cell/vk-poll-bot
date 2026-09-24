from dataclasses import dataclass
from typing import Literal


Choice = Literal["yes", "no"]


@dataclass(frozen=True)
class Counts:
    yes: int
    no: int
    manual_yes: int

    @property
    def total_yes(self) -> int:
        return self.yes + self.manual_yes


def set_vote(state: dict, user_id: int, name: str, choice: Choice) -> None:
    state.setdefault("voters", {})[str(user_id)] = {"name": name, "choice": choice}


def counts(state: dict) -> Counts:
    voters = state.get("voters", {}).values()
    return Counts(
        yes=sum(voter.get("choice") == "yes" for voter in voters),
        no=sum(voter.get("choice") == "no" for voter in voters),
        manual_yes=len(state.get("manual_yes_voters", {})),
    )


def format_status(state: dict, threshold: int) -> str:
    result = counts(state)
    return (
        f"ДА: {result.yes} + {result.manual_yes} приглашённых = "
        f"{result.total_yes} / {threshold}\nНет: {result.no}"
    )


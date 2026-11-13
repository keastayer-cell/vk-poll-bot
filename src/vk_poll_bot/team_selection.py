from __future__ import annotations

import secrets
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable

from .text_tables import player_row

HISTORY_LIMIT = 5


class NoAlternative(ValueError):
    pass


def partition(teams: list[list[str]]) -> frozenset:
    """Ignore team numbers, colours and order within each squad."""
    return frozenset(frozenset(team) for team in teams)


def valid_teams(teams: object, expected: set[str] | None = None) -> bool:
    if not isinstance(teams, list) or len(teams) not in {2, 3}:
        return False
    if any(not isinstance(team, list) or not team for team in teams):
        return False
    ids = [key for team in teams for key in team]
    return (all(isinstance(key, str) and key for key in ids)
            and len(ids) == len(set(ids)) and 8 <= len(ids) <= 16
            and (expected is None or set(ids) == expected))


def distribution_teams(distribution: dict | None) -> list[list[str]] | None:
    """Read IDs, or recover an unambiguous pre-update lineup from its saved snapshot."""
    if not distribution or distribution.get("invalidated"):
        return None
    fields = [p for p in distribution.get("snapshot", {}).get("players", [])
              if p.get("position") == "field"]
    expected = {p["id"] for p in fields}
    if "teams" in distribution:
        teams = distribution["teams"]
        return teams if valid_teams(teams, expected) else None
    rows: dict[str, list[str]] = {}
    for player in fields:
        rows.setdefault(player_row(player), []).append(player["id"])
    sections = distribution.get("text", "").split("🧤 Вратари", 1)[0].split("⚽ КОМАНДА")[1:]
    teams = []
    for section in sections:
        team = []
        for line in section.splitlines():
            matches = rows.get(line, [])
            if len(matches) > 1:
                return None
            team.extend(matches)
        teams.append(team)
    return teams if valid_teams(teams, expected) else None


@dataclass
class TeamSelection:
    history: list[list[list[str]]] = field(default_factory=list)
    previous: list[list[str]] | None = None
    chooser: Callable = secrets.choice
    teams: list[list[str]] = field(default_factory=list, init=False)

    def select(self, candidates: list, players: list[dict], score: Callable) -> list:
        # Keep the existing best balance exactly; variety never buys a weaker balance.
        best_score = min(score(candidate) for candidate in candidates)
        excluded = partition(self.previous) if self.previous else None
        options = {}
        for candidate in candidates:
            if score(candidate) != best_score:
                continue
            groups = candidate[-1]
            ids = [[players[i]["id"] for i in group] for group in groups]
            key = partition(ids)
            if key != excluded:
                options.setdefault(key, (groups, ids))
        if not options:
            raise NoAlternative(
                "⚠️ Другого распределения с таким же качеством баланса нет. "
                "Прежние составы сохранены."
            )
        pairs: Counter = Counter()
        for weight, teams in enumerate(self.history[-HISTORY_LIMIT:], 1):
            for team in teams:
                for pair in combinations(sorted(team), 2):
                    pairs[pair] += weight

        def repeats(option):
            return sum(pairs[pair] for team in option[1]
                       for pair in combinations(sorted(team), 2))

        minimum = min(repeats(option) for option in options.values())
        groups, ids = self.chooser([option for option in options.values()
                                   if repeats(option) == minimum])
        self.teams = ids
        return groups

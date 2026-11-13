from copy import deepcopy

import pytest

from vk_poll_bot.models import normalize_state
from vk_poll_bot.team_selection import (
    NoAlternative,
    TeamSelection,
    distribution_teams,
    partition,
)
from vk_poll_bot.teams import (
    balanced_teams,
    balanced_three_with_substitutes,
    balanced_with_substitutes,
    teams_text,
)


def players(count, ratings=None):
    return [{"id": str(i), "name": f"Игрок {i}", "position": "field",
             "rating": ratings[i] if ratings else 2} for i in range(count)]


def ids(teams):
    return [[p["id"] for p in team] for team in teams]


@pytest.mark.parametrize("count,build", [
    (8, lambda p, s: balanced_teams(p, team_size=4, selection=s)),
    (12, lambda p, s: balanced_teams(p, team_size=4, selection=s)),
    (13, lambda p, s: balanced_three_with_substitutes(p, selection=s)),
    (14, lambda p, s: balanced_three_with_substitutes(p, selection=s)),
    (11, lambda p, s: balanced_with_substitutes(p, selection=s)),
    (16, lambda p, s: balanced_with_substitutes(p, selection=s)),
])
def test_choice_and_redraw_change_memberships_without_losing_players(count, build):
    roster = players(count)
    pool_sizes = []

    def choose(options):
        pool_sizes.append(len(options))
        return options[-1]

    first = TeamSelection(chooser=choose)
    a = build(roster, first)
    second = TeamSelection(previous=first.teams, chooser=choose)
    b = build(roster, second)
    assert pool_sizes[0] > 1
    assert partition(ids(a)) != partition(ids(b))
    assert sorted(p["id"] for t in b for p in t) == sorted(p["id"] for p in roster)
    assert sorted(map(len, a)) == sorted(map(len, b))
    assert max(sum(p["rating"] for p in t) / len(t) for t in b) == 2


def test_history_avoids_repeated_pairs_before_random_tie_break():
    roster = players(8)
    old = ids(balanced_teams(roster, team_size=4))
    selection = TeamSelection(history=[old], chooser=lambda options: options[0])
    result = balanced_teams(roster, team_size=4, selection=selection)
    # Each new squad takes two from each previous squad: four repeated pairs, not twelve.
    for team in result:
        assert len(set(p["id"] for p in team) & set(old[0])) == 2
    assert partition(selection.teams) != partition(old)


def test_candidates_outside_best_balance_cannot_be_selected_for_variety():
    roster = players(8, [1, 1, 2, 2, 3, 3, 4, 4])
    old = ids(balanced_teams(roster, team_size=4))
    selection = TeamSelection(history=[old], previous=old, chooser=lambda options: options[-1])
    result = balanced_teams(roster, team_size=4, selection=selection)
    assert all(sorted(p["rating"] for p in team) == [1, 2, 3, 4] for team in result)
    assert partition(selection.teams) != partition(old)


def test_no_alternative_when_only_team_labels_change():
    roster = players(8)
    groups = [(0, 1, 2, 3), (4, 5, 6, 7)]
    previous = [[str(i) for i in group] for group in groups]
    selection = TeamSelection(previous=previous)
    with pytest.raises(NoAlternative, match="Прежние составы сохранены"):
        selection.select([(0, groups), (0, list(reversed(groups)))], roster, lambda c: c[0])
    assert not selection.teams


def test_read_legacy_lineup_from_saved_rows_without_guessing_duplicate_names():
    roster = players(12, [1, 2, 3, 4] * 3)
    directory = {p["id"]: p for p in roster}
    poll = {"voters": {key: {"name": p["name"], "choice": "yes"}
                       for key, p in directory.items()}}
    distribution = {"snapshot": {"players": roster}, "text": teams_text(poll, directory)}
    teams = distribution_teams(distribution)
    assert teams and set().union(*map(set, teams)) == set(directory)
    # Names changed since publication do not affect reading the saved snapshot.
    directory = deepcopy(directory)
    directory["0"]["name"] = "Новое имя"
    assert distribution_teams(distribution) == teams
    distribution["snapshot"]["players"][1]["name"] = roster[0]["name"]
    distribution["snapshot"]["players"][1]["rating"] = roster[0]["rating"]
    assert distribution_teams(distribution) is None


def test_legacy_state_keeps_votes_ratings_and_empty_history():
    before = {"players": {"x": {"name": "Вымышленный", "rating": 2}},
              "attendance": {"players": {}, "polls": {}}, "rating_order": "lower"}
    after = normalize_state(deepcopy(before), {})
    assert after["team_history"] == []
    for key in before:
        assert after[key] == before[key]


@pytest.mark.parametrize("history", [None, {}, [{"poll_id": "x", "teams": []}],
                                      [{"poll_id": "x", "poll_date": "2026-01-01",
                                        "teams": [["a"] * 4, ["b"] * 4]}]])
def test_corrupt_history_is_rejected(history):
    with pytest.raises(ValueError, match="team_history"):
        normalize_state({"team_history": history}, {})

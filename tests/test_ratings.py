import pytest

from vk_poll_bot.ratings import format_rating, parse_rating, rating_units, valid_rating
from vk_poll_bot.teams import balanced_five_four_four, balanced_with_substitutes, poll_players


@pytest.mark.parametrize("text,expected", [
    ("5,5", 5.5), ("7.5", 7.5), ("10", 10), ("6", 6),
    ("6,4", 6.4), ("6.4", 6.4), ("5,3", 5.3), ("1,1", 1.1), ("9.9", 9.9),
])
def test_parses_and_formats_whole_and_decimal_ratings(text, expected):
    assert parse_rating(text) == expected
    assert valid_rating(expected)
    assert "." not in format_rating(expected)


@pytest.mark.parametrize("text", ["5,35", "10,1", "0,9", "nan", "inf", "abc"])
def test_rejects_invalid_ratings(text):
    with pytest.raises(ValueError):
        parse_rating(text)
    assert not valid_rating(True)
    assert not valid_rating(6.45)


def test_half_ratings_are_preserved_in_poll_and_balancing():
    players = [{"id": str(i), "name": str(i), "rating": 5.5 if i % 2 else 6.5,
                "position": "field"} for i in range(13)]
    poll = {"voters": {"0": {"name": "0", "choice": "yes"}}}
    assert poll_players(poll, {"0": players[0]})[0]["rating"] == 6.5
    teams = balanced_five_four_four(players)
    assert sorted(p["rating"] for t in teams for p in t) == sorted(p["rating"] for p in players)
    assert all(sum(p["rating"] for p in teams[0]) * 4 >= sum(p["rating"] for p in t) * 5
               for t in teams[1:])


def test_all_tenths_are_valid_and_round_trip_exactly():
    for units in range(10, 101):
        value = parse_rating(f"{units // 10},{units % 10}")
        assert valid_rating(value)
        assert rating_units(value) == units
        assert parse_rating(format_rating(value)) == value


@pytest.mark.parametrize("size", [9, 11, 13])
def test_unequal_teams_balance_decimal_ratings_without_float_comparisons(size):
    ratings = [6.4, 5.3, 7.1, 2.2, 8.8, 4.9, 6.7, 7.6, 3.1, 5.8, 9.3, 6.1, 4.4]
    players = [{"id": str(i), "rating": rating} for i, rating in enumerate(ratings[:size])]
    teams = (balanced_five_four_four(players) if size == 13 else balanced_with_substitutes(players))
    assert sorted(p["id"] for t in teams for p in t) == sorted(p["id"] for p in players)
    totals = [sum(rating_units(p["rating"]) for p in t) for t in teams]
    assert all(totals[0] * len(t) >= totals[i] * len(teams[0])
               for i, t in enumerate(teams[1:], 1))

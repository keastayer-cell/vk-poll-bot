import pytest

from vk_poll_bot.ratings import format_rating, parse_rating, valid_rating
from vk_poll_bot.teams import balanced_five_four_four, poll_players


@pytest.mark.parametrize("text,expected", [("5,5", 5.5), ("7.5", 7.5), ("10", 10), ("6", 6)])
def test_parses_and_formats_whole_and_half_ratings(text, expected):
    assert parse_rating(text) == expected
    assert valid_rating(expected)
    assert "." not in format_rating(expected)


@pytest.mark.parametrize("text", ["5,3", "10,5", "0,5", "nan", "inf", "abc"])
def test_rejects_invalid_ratings(text):
    with pytest.raises(ValueError):
        parse_rating(text)
    assert not valid_rating(True)


def test_half_ratings_are_preserved_in_poll_and_balancing():
    players = [{"id": str(i), "name": str(i), "rating": 5.5 if i % 2 else 6.5,
                "position": "field"} for i in range(13)]
    poll = {"voters": {"0": {"name": "0", "choice": "yes"}}}
    assert poll_players(poll, {"0": players[0]})[0]["rating"] == 6.5
    teams = balanced_five_four_four(players)
    assert sorted(p["rating"] for t in teams for p in t) == sorted(p["rating"] for p in players)
    assert all(sum(p["rating"] for p in teams[0]) * 4 >= sum(p["rating"] for p in t) * 5
               for t in teams[1:])

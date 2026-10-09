from __future__ import annotations

from .ratings import format_rating


def player_row(player: dict) -> str:
    """Put the fixed-width rating first: proportional names cannot shift it.

    U+2007 is a figure space, matching a digit's width in proportional fonts.
    No trailing padding or monospaced rendering is assumed for VK names.
    """
    if player.get("position") == "goalkeeper":
        value = "🧤"
    else:
        rating = player.get("rating")
        if rating is None:
            value = "\u2007—\u2008\u2007"
        else:
            whole, _, fraction = format_rating(rating).partition(",")
            # Reserve two digit widths, one comma width and one fractional digit.
            value = "\u2007" * (2 - len(whole)) + whole
            value += "," + fraction if fraction else "\u2008\u2007"
    return f"{value} │ {player['name']}"

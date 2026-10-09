from vk_poll_bot.text_tables import player_row


def test_rating_column_does_not_depend_on_name_length():
    for name in ("Иван", "Александр Константиновский"):
        assert player_row({"name": name, "rating": 7}) == f"\u20077\u2008\u2007 │ {name}"
        assert player_row({"name": name, "rating": 10}) == f"10\u2008\u2007 │ {name}"
        assert player_row({"name": name, "rating": 7.5}) == f"\u20077,5 │ {name}"
    assert player_row({"name": "Антон", "position": "goalkeeper"}) == "🧤 │ Антон"

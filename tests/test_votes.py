from vk_poll_bot.models import new_poll_state
from vk_poll_bot.votes import counts, format_status, set_vote


def test_vote_can_be_changed() -> None:
    state = new_poll_state("2026-09-24", "Идете?")
    set_vote(state, 10, "Антон", "yes")
    set_vote(state, 10, "Антон", "no")

    result = counts(state)

    assert result.yes == 0
    assert result.no == 1


def test_manual_votes_are_included_in_total() -> None:
    state = new_poll_state("2026-09-24", "Идете?")
    set_vote(state, 10, "Антон", "yes")
    state["manual_yes_voters"]["manual:1"] = "Иван"

    assert format_status(state, 10) == "ДА: 1 + 1 приглашённых = 2 / 10\nНет: 0"


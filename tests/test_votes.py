from vk_poll_bot.models import new_poll_state
from vk_poll_bot.votes import (
    counts,
    evaluate_threshold,
    format_status,
    parse_plus_one,
    remove_vote,
    set_vote,
)


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

    assert format_status(state, 10) == "«ДА»: 1 + 1 вручную = 2 / 10\n«Нет»: 0"


def test_cancel_yes_vote_keeps_name_for_quorum_notification() -> None:
    state = new_poll_state("2026-09-24", "Идете?")
    set_vote(state, 10, "Антон", "yes")

    removed = remove_vote(state, 10)

    assert removed == {"name": "Антон", "choice": "yes"}
    assert state["last_removed_yes_label"] == "Антон"


def test_threshold_and_quorum_loss_notifications() -> None:
    state = new_poll_state("2026-09-24", "Идете?")
    set_vote(state, 1, "Первый", "yes")
    assert [event.text for event in evaluate_threshold(state, 2)] == ["Братики, еще 1 и идем 💪"]

    set_vote(state, 2, "Второй", "yes")
    assert len(evaluate_threshold(state, 2)) == 2

    set_vote(state, 2, "Второй", "no")
    assert "Нас снова не хватает" in evaluate_threshold(state, 2)[0].text


def test_plus_one_parser_accepts_compact_form() -> None:
    assert parse_plus_one("+1Иванов", "Антон") == "Иванов"
    assert parse_plus_one("+1", "Антон") == "Гость от Антон"
    assert parse_plus_one("со мной +1 Иванов", "Антон") is None

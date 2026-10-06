"""Tests for key-moment extraction (no Azure calls)."""

from inside_the_game import stats
from inside_the_game.generator import FICTIONAL_TEAMS, generate_match
from inside_the_game.moments import extract_moments
from inside_the_game.store import moment_to_doc

MATCH = generate_match(5)
MOMENTS = extract_moments(MATCH)


def test_every_goal_and_counterattack_becomes_exactly_one_moment() -> None:
    possession_of = {e.event_id: e.possession_id for e in MATCH.events}
    goal_possessions = {possession_of[g["event_id"]] for g in stats.goals(MATCH)}
    counter_possessions = {c["possession_id"] for c in stats.counterattacks(MATCH)}
    moment_possessions = [int(m.moment_id.rsplit("-p", 1)[1]) for m in MOMENTS]
    assert sorted(moment_possessions) == sorted(goal_possessions | counter_possessions)


def test_kinds_and_scores_match_the_stats() -> None:
    goals = {g["event_id"]: g for g in stats.goals(MATCH)}
    for moment in MOMENTS:
        goal = goals.get(moment.event_ids[-1])
        if goal:
            assert moment.kind in ("goal", "counterattack goal")
            assert moment.score_after == goal["score_after"]
            assert moment.minute == goal["minute"]
        else:
            assert moment.kind == "counterattack"
            assert moment.score_after == moment.score_before


def test_descriptions_are_deterministic_and_never_name_teams() -> None:
    assert [m.description for m in extract_moments(generate_match(5))] == [m.description for m in MOMENTS]
    for moment in MOMENTS:
        assert not any(team in moment.description for team in FICTIONAL_TEAMS)
        assert " a interception" not in moment.description


def test_example_description() -> None:
    winner = next(m for m in MOMENTS if m.minute == 80)
    assert winner.moment_id == "match_005-p227"
    assert winner.description == (
        "Late in the game, minute 80, with the score level: a counterattack goal that put the team ahead. "
        "The attack started after winning the ball with an interception in its own half, "
        "then 3 passes before a shot from inside the box, from a wide angle."
    )


def test_moment_document_holds_the_embedding() -> None:
    doc = moment_to_doc(MOMENTS[0], [0.1, 0.2])
    assert doc["id"] == MOMENTS[0].moment_id
    assert doc["match_id"] == "match_005"
    assert doc["embedding"] == [0.1, 0.2]

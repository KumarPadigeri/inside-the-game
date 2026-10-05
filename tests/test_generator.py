"""Tests for the synthetic match generator."""

from pathlib import Path

import pytest

from inside_the_game.generator import (
    EVENT_OUTCOMES,
    FICTIONAL_TEAMS,
    Match,
    generate_match,
    load_match,
    save_match,
)


@pytest.fixture(scope="module")
def match() -> Match:
    return generate_match(seed=1)


def test_same_seed_gives_same_match() -> None:
    assert generate_match(7).to_dict() == generate_match(7).to_dict()


def test_different_seeds_give_different_matches() -> None:
    assert generate_match(1).to_dict() != generate_match(2).to_dict()


def test_event_ids_are_unique_and_sequential(match: Match) -> None:
    assert [e.event_id for e in match.events] == list(range(1, len(match.events) + 1))


def test_minutes_never_go_backwards_and_cover_the_match(match: Match) -> None:
    minutes = [e.minute for e in match.events]
    assert minutes == sorted(minutes)
    assert minutes[0] == 0
    assert 90 <= minutes[-1] <= 96


def test_possession_ids_never_go_backwards(match: Match) -> None:
    ids = [e.possession_id for e in match.events]
    assert ids == sorted(ids)


def test_each_possession_belongs_to_one_team(match: Match) -> None:
    owner: dict[int, str] = {}
    for e in match.events:
        assert owner.setdefault(e.possession_id, e.team) == e.team


def test_positions_are_on_the_pitch(match: Match) -> None:
    for e in match.events:
        assert 0 <= e.x <= 100 and 0 <= e.y <= 100


def test_types_and_outcomes_are_valid(match: Match) -> None:
    for e in match.events:
        assert e.type in EVENT_OUTCOMES
        assert e.outcome in EVENT_OUTCOMES[e.type]


def test_players_match_their_team(match: Match) -> None:
    for e in match.events:
        prefix = "H" if e.team == "Home" else "A"
        assert e.player[0] == prefix
        assert 1 <= int(e.player[1:]) <= 11


def test_teams_are_fictional_and_different(match: Match) -> None:
    assert match.home_team in FICTIONAL_TEAMS
    assert match.away_team in FICTIONAL_TEAMS
    assert match.home_team != match.away_team


def test_every_goal_is_followed_by_a_kickoff_for_the_other_team(match: Match) -> None:
    for i, e in enumerate(match.events[:-1]):
        if e.type == "shot" and e.outcome == "goal":
            nxt = match.events[i + 1]
            assert nxt.type == "kickoff"
            assert nxt.team != e.team


def test_scores_and_shots_are_realistic_on_average() -> None:
    matches = [generate_match(seed) for seed in range(1, 51)]
    goals = [sum(m.score().values()) for m in matches]
    shots = [sum(e.type == "shot" for e in m.events) for m in matches]
    assert 1.5 <= sum(goals) / len(goals) <= 4.0
    assert 15 <= sum(shots) / len(shots) <= 35


def test_save_and_load_round_trip(match: Match, tmp_path: Path) -> None:
    path = save_match(match, tmp_path)
    assert path.name == "match_001.json"
    assert load_match(path).to_dict() == match.to_dict()

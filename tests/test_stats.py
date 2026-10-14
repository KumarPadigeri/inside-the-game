"""Tests for the match statistics, using a small hand-made match with known answers."""

import pytest

from inside_the_game.generator import Event, Match, generate_match
from inside_the_game.stats import (
    counterattacks,
    goals,
    momentum,
    pass_difficulty,
    pass_quality,
    player_stats,
    players,
    possession,
    pressing,
    shots,
)

# (minute, team, player, type, x, y, outcome, possession_id)
_ROWS = [
    # Possession 1, Home: kickoff, two passes, goal.
    (0, "Home", "H7", "kickoff", 50, 50, "complete", 1),
    (0, "Home", "H7", "pass", 50, 50, "complete", 1),
    (1, "Home", "H8", "pass", 60, 45, "complete", 1),
    (1, "Home", "H9", "shot", 90, 50, "goal", 1),
    # Possession 2, Away: kickoff, misplaced pass.
    (2, "Away", "A7", "kickoff", 50, 50, "complete", 2),
    (2, "Away", "A6", "pass", 50, 50, "incomplete", 2),
    # Possession 3, Home: interception in own half, two passes, shot saved -> COUNTER.
    (10, "Home", "H4", "interception", 40, 40, "won", 3),
    (10, "Home", "H4", "pass", 40, 40, "complete", 3),
    (10, "Home", "H7", "pass", 65, 50, "complete", 3),
    (11, "Home", "H10", "shot", 85, 55, "saved", 3),
    # Possession 4, Away: goal kick, two passes, lost to a tackle.
    (11, "Away", "A1", "pass", 8, 50, "complete", 4),
    (12, "Away", "A3", "pass", 30, 40, "complete", 4),
    # Possession 5, Home: tackle in the OPPONENT half, shot missed -> not a counter.
    (12, "Home", "H6", "tackle", 70, 60, "won", 5),
    (12, "Home", "H9", "shot", 85, 40, "missed", 5),
    # Possession 6, Away: goal kick, one pass, shot blocked.
    (13, "Away", "A1", "pass", 10, 50, "complete", 6),
    (14, "Away", "A9", "shot", 80, 50, "blocked", 6),
    # Possession 7, Away: interception in own half but FIVE passes -> not a counter.
    (20, "Away", "A5", "interception", 30, 50, "won", 7),
    (20, "Away", "A5", "pass", 30, 50, "complete", 7),
    (20, "Away", "A6", "pass", 40, 50, "complete", 7),
    (21, "Away", "A7", "pass", 50, 50, "complete", 7),
    (21, "Away", "A8", "pass", 60, 50, "complete", 7),
    (21, "Away", "A10", "pass", 75, 50, "incomplete", 7),
]


@pytest.fixture
def match() -> Match:
    events = [
        Event(i, minute, team, player, type_, x, y, outcome, pid)
        for i, (minute, team, player, type_, x, y, outcome, pid) in enumerate(_ROWS, start=1)
    ]
    return Match(match_id="test", seed=0, home_team="Northbridge FC", away_team="Riverside Athletic", events=events)


def test_possession(match: Match) -> None:
    result = possession(match)
    # Home 4 passes, Away 9 passes (7 complete).
    assert result["Home"] == {"percent": 30.8, "passes_attempted": 4, "passes_completed": 4, "pass_accuracy": 100.0}
    assert result["Away"] == {"percent": 69.2, "passes_attempted": 9, "passes_completed": 7, "pass_accuracy": 77.8}


def test_possession_percentages_add_up_to_100() -> None:
    result = possession(generate_match(3))
    assert result["Home"]["percent"] + result["Away"]["percent"] == pytest.approx(100.0)


def test_possession_with_no_passes() -> None:
    empty = Match(match_id="empty", seed=0, home_team="A", away_team="B", events=[])
    assert possession(empty)["Home"] == {"percent": 0.0, "passes_attempted": 0, "passes_completed": 0, "pass_accuracy": 0.0}


def test_shots(match: Match) -> None:
    result = shots(match)
    assert result["Home"] == {
        "total": 3, "on_target": 2, "goals": 1, "saved": 1, "missed": 1, "blocked": 0, "event_ids": [4, 10, 14],
    }
    assert result["Away"] == {
        "total": 1, "on_target": 0, "goals": 0, "saved": 0, "missed": 0, "blocked": 1, "event_ids": [16],
    }


def test_goals(match: Match) -> None:
    assert goals(match) == [
        {
            "event_id": 4,
            "minute": 1,
            "team": "Home",
            "player": "H9",
            "score_after": "1-0",
            "buildup_event_ids": [1, 2, 3, 4],
        }
    ]


def test_goals_agree_with_the_scoreline() -> None:
    match = generate_match(5)
    result = goals(match)
    score = match.score()
    assert len(result) == score["Home"] + score["Away"]
    if result:
        assert result[-1]["score_after"] == f"{score['Home']}-{score['Away']}"


def test_counterattacks(match: Match) -> None:
    assert counterattacks(match) == [
        {
            "possession_id": 3,
            "team": "Home",
            "minute": 11,
            "won_by": "interception",
            "won_at_x": 40,
            "passes": 2,
            "outcome": "saved",
            "event_ids": [7, 8, 9, 10],
        }
    ]


def test_every_evidence_id_exists_in_the_match() -> None:
    match = generate_match(1)
    known = {e.event_id for e in match.events}
    for team_shots in shots(match).values():
        assert set(team_shots["event_ids"]) <= known
    for goal in goals(match):
        assert set(goal["buildup_event_ids"]) <= known
    for counter in counterattacks(match):
        assert set(counter["event_ids"]) <= known


def test_player_stats_for_a_scorer(match: Match) -> None:
    h9 = player_stats(match, "H9")
    assert h9["team"] == "Home"
    assert (h9["shots"], h9["shots_on_target"]) == (2, 1)
    assert h9["goals"] == [{"event_id": 4, "minute": 1, "score_after": "1-0"}]
    assert h9["set_up_goals"] == []  # his own goal is in "goals", not here
    assert h9["passes_attempted"] == 0 and h9["pass_accuracy"] == 0.0
    assert (h9["first_minute"], h9["last_minute"]) == (1, 12)
    assert h9["event_ids"] == [4, 14]


def test_player_stats_for_a_ball_winner_who_started_a_counter(match: Match) -> None:
    h4 = player_stats(match, "H4")
    assert h4["interceptions_won"] == 1 and h4["tackles_won"] == 0
    assert (h4["passes_attempted"], h4["passes_completed"], h4["pass_accuracy"]) == (1, 1, 100.0)
    assert [(c["minute"], c["outcome"]) for c in h4["counterattacks"]] == [(11, "saved")]
    assert h4["event_ids"] == [7]


def test_player_stats_count_goals_set_up_by_being_in_the_build_up(match: Match) -> None:
    h7 = player_stats(match, "H7")
    assert h7["passes_attempted"] == 2  # the kickoff is not a pass
    assert [g["minute"] for g in h7["set_up_goals"]] == [1]
    assert len(h7["counterattacks"]) == 1


def test_player_stats_reject_a_player_who_did_not_play(match: Match) -> None:
    with pytest.raises(ValueError, match="H11"):
        player_stats(match, "H11")


def test_players_lists_home_then_away_by_shirt_number(match: Match) -> None:
    listed = players(match)
    assert listed[:3] == ["H4", "H6", "H7"]
    assert listed.index("H10") < listed.index("A1")
    assert listed[-1] == "A10"


def test_momentum_windows_cover_the_match(match: Match) -> None:
    windows = momentum(match)
    # Events run to minute 21: windows 0-14 and 15-21 (a 7-minute tail is long enough to be its own window).
    assert [(w["start_minute"], w["end_minute"]) for w in windows] == [(0, 14), (15, 21)]
    first, second = windows
    assert first["goals"] == [4]
    assert first["shots"] == {"Home": 3, "Away": 1}
    assert first["possession_changes"] == 5  # possessions 1-6 in the first window
    # Home's attacking-third passes: none (x 40-65); Away's: none either -> even, 0% each.
    assert first["field_tilt"] == {"Home": 0.0, "Away": 0.0} and first["control"] == "even"
    # Second window: Away's possession 7 has one pass at x=75 in the attacking third.
    assert second["field_tilt"] == {"Home": 0.0, "Away": 100.0} and second["control"] == "Away"
    assert second["possession"] == {"Home": 0.0, "Away": 100.0}


def test_momentum_tempo_compares_with_the_match_average() -> None:
    windows = momentum(generate_match(2))
    assert {w["tempo"] for w in windows} <= {"frantic", "steady", "normal"}
    assert windows[-1]["end_minute"] == generate_match(2).events[-1].minute


def test_pressing_counts_where_the_ball_was_won(match: Match) -> None:
    home = pressing(match)["Home"]
    # H4 interception at x=40 (middle) started a shot; H6 tackle at x=70 (high) led to a missed shot.
    assert (home["ball_wins"], home["high"], home["middle"], home["deep"]) == (2, 1, 1, 0)
    assert home["high_win_shots"] == 1 and home["high_win_goals"] == 0
    assert home["high_win_event_ids"] == [13]
    away = pressing(match)["Away"]
    assert (away["ball_wins"], away["deep"], away["high_win_shots"]) == (1, 1, 0)


def test_pass_difficulty_rating() -> None:
    assert pass_difficulty(5, 0, 40) == 1  # short, sideways, own half
    assert pass_difficulty(45, 30, 80) == 5  # long, forward, into the attacking third
    assert pass_difficulty(25, 16, 50) == 3


def test_pass_quality_measures_distance_to_the_next_event(match: Match) -> None:
    home = pass_quality(match)["Home"]
    # H7 (50,50) -> H8 (60,45): 10.5 m forward, 3.4 m across; H8 (60,45) -> H9 (90,50): 31.5 m, long.
    # H4 (40,40) -> H7 (65,50); H7 (65,50) -> H10 (85,55).
    assert home["passes_measured"] == 4
    assert home["long_passes"] == 1 and home["long_pass_accuracy"] == 100.0
    assert home["progressive_passes"] == 3
    assert 1 <= home["average_difficulty"] <= 5
    away = pass_quality(match)["Away"]
    assert away["passes_measured"] >= 1

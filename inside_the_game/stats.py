"""Deterministic match statistics.

These functions are the "numbers come from code" half of the project: agents
call them as tools instead of calculating anything themselves. Every result
carries the event_ids that prove it, so each recap sentence can link to its
evidence.
"""

from __future__ import annotations

from itertools import groupby
from typing import TypedDict

from inside_the_game.generator import Event, Match, Team

TEAMS: tuple[Team, Team] = ("Home", "Away")

# A counterattack: ball won in your own half, then a shot within this many passes.
COUNTER_MAX_PASSES = 4


class PossessionStats(TypedDict):
    percent: float  # share of all passes in the match
    passes: int
    pass_accuracy: float  # percent of passes completed


class ShotStats(TypedDict):
    total: int
    on_target: int  # goals + saved
    goals: int
    saved: int
    missed: int
    blocked: int
    event_ids: list[int]


class Goal(TypedDict):
    event_id: int
    minute: int
    team: Team
    player: str
    score_after: str  # "Home-Away", e.g. "2-1"
    buildup_event_ids: list[int]  # the whole possession that led to the goal


class Counterattack(TypedDict):
    possession_id: int
    team: Team
    minute: int  # minute of the shot
    won_by: str  # "tackle" or "interception"
    won_at_x: int
    passes: int
    outcome: str  # how the shot ended: goal, saved, missed or blocked
    event_ids: list[int]


def _percent(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _possessions(match: Match) -> list[list[Event]]:
    """Split the events into possessions (one attack each)."""
    return [list(events) for _, events in groupby(match.events, key=lambda e: e.possession_id)]


def possession(match: Match) -> dict[Team, PossessionStats]:
    """Possession per team, measured as each team's share of all passes."""
    passes = {team: [e for e in match.events if e.team == team and e.type == "pass"] for team in TEAMS}
    total = sum(len(p) for p in passes.values())
    home_percent = _percent(len(passes["Home"]), total)
    percents = {"Home": home_percent, "Away": round(100 - home_percent, 1) if total else 0.0}
    return {
        team: {
            "percent": percents[team],
            "passes": len(passes[team]),
            "pass_accuracy": _percent(sum(e.outcome == "complete" for e in passes[team]), len(passes[team])),
        }
        for team in TEAMS
    }


def shots(match: Match) -> dict[Team, ShotStats]:
    """Shot counts per team, broken down by outcome."""
    result: dict[Team, ShotStats] = {}
    for team in TEAMS:
        team_shots = [e for e in match.events if e.team == team and e.type == "shot"]
        outcomes = [e.outcome for e in team_shots]
        result[team] = {
            "total": len(team_shots),
            "on_target": outcomes.count("goal") + outcomes.count("saved"),
            "goals": outcomes.count("goal"),
            "saved": outcomes.count("saved"),
            "missed": outcomes.count("missed"),
            "blocked": outcomes.count("blocked"),
            "event_ids": [e.event_id for e in team_shots],
        }
    return result


def goals(match: Match) -> list[Goal]:
    """Every goal in order, with the running score and its build-up."""
    result: list[Goal] = []
    score = {"Home": 0, "Away": 0}
    for events in _possessions(match):
        last = events[-1]
        if last.type == "shot" and last.outcome == "goal":
            score[last.team] += 1
            result.append(
                {
                    "event_id": last.event_id,
                    "minute": last.minute,
                    "team": last.team,
                    "player": last.player,
                    "score_after": f"{score['Home']}-{score['Away']}",
                    "buildup_event_ids": [e.event_id for e in events],
                }
            )
    return result


def counterattacks(match: Match) -> list[Counterattack]:
    """Attacks where a team won the ball in its own half and shot quickly.

    Rule: the possession starts with a tackle or interception at x < 50 and
    ends in a shot after at most COUNTER_MAX_PASSES passes.
    """
    result: list[Counterattack] = []
    for events in _possessions(match):
        first, last = events[0], events[-1]
        n_passes = sum(e.type == "pass" for e in events)
        if (
            first.type in ("tackle", "interception")
            and first.x < 50
            and last.type == "shot"
            and n_passes <= COUNTER_MAX_PASSES
        ):
            result.append(
                {
                    "possession_id": first.possession_id,
                    "team": first.team,
                    "minute": last.minute,
                    "won_by": first.type,
                    "won_at_x": first.x,
                    "passes": n_passes,
                    "outcome": last.outcome,
                    "event_ids": [e.event_id for e in events],
                }
            )
    return result

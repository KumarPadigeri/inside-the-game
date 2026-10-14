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
    passes_attempted: int
    passes_completed: int
    pass_accuracy: float  # percent of attempted passes that were completed


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
    result: dict[Team, PossessionStats] = {}
    for team in TEAMS:
        completed = sum(e.outcome == "complete" for e in passes[team])
        result[team] = {
            "percent": percents[team],
            "passes_attempted": len(passes[team]),
            "passes_completed": completed,
            "pass_accuracy": _percent(completed, len(passes[team])),
        }
    return result


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


class PlayerGoal(TypedDict):
    event_id: int
    minute: int
    score_after: str  # "Home-Away"


class PlayerMove(TypedDict):
    """A goal or counterattack the player took part in (without scoring it)."""

    minute: int
    outcome: str  # for a goal: "goal"; for a counterattack: how its shot ended
    event_ids: list[int]


class PlayerStats(TypedDict):
    player: str
    team: Team
    first_minute: int  # first and last minute the player touched the ball
    last_minute: int
    passes_attempted: int
    passes_completed: int
    pass_accuracy: float
    shots: int
    shots_on_target: int
    goals: list[PlayerGoal]
    tackles_won: int
    interceptions_won: int
    set_up_goals: list[PlayerMove]  # teammates' goals where the player was in the build-up
    counterattacks: list[PlayerMove]  # counterattacks the player was part of
    event_ids: list[int]  # the player's shots and ball wins: the moments that show their game


def player_stats(match: Match, player: str) -> PlayerStats:
    """One player's match, from their own events: passing, shooting, winning the ball,
    and the goals and counterattacks they were part of.

    Raises ValueError if the player has no events in this match.
    """
    mine = [e for e in match.events if e.player == player]
    if not mine:
        raise ValueError(f"Player {player!r} has no events in {match.match_id}")
    passes = [e for e in mine if e.type == "pass"]
    shots_taken = [e for e in mine if e.type == "shot"]
    completed = sum(e.outcome == "complete" for e in passes)
    my_ids = {e.event_id for e in mine}
    all_goals = goals(match)
    return {
        "player": player,
        "team": mine[0].team,
        "first_minute": mine[0].minute,
        "last_minute": mine[-1].minute,
        "passes_attempted": len(passes),
        "passes_completed": completed,
        "pass_accuracy": _percent(completed, len(passes)),
        "shots": len(shots_taken),
        "shots_on_target": sum(e.outcome in ("goal", "saved") for e in shots_taken),
        "goals": [
            {"event_id": g["event_id"], "minute": g["minute"], "score_after": g["score_after"]}
            for g in all_goals
            if g["player"] == player
        ],
        "tackles_won": sum(e.type == "tackle" and e.outcome == "won" for e in mine),
        "interceptions_won": sum(e.type == "interception" and e.outcome == "won" for e in mine),
        "set_up_goals": [
            {"minute": g["minute"], "outcome": "goal", "event_ids": g["buildup_event_ids"]}
            for g in all_goals
            if g["player"] != player and my_ids & set(g["buildup_event_ids"])
        ],
        "counterattacks": [
            {"minute": c["minute"], "outcome": c["outcome"], "event_ids": c["event_ids"]}
            for c in counterattacks(match)
            if my_ids & set(c["event_ids"])
        ],
        "event_ids": [e.event_id for e in mine if e.type in ("shot", "tackle", "interception")],
    }


def players(match: Match) -> list[str]:
    """Everyone who touched the ball, home players first, by shirt number."""
    seen = {(e.team, e.player) for e in match.events}
    return [p for _, p in sorted(seen, key=lambda tp: (tp[0] != "Home", int(tp[1][1:])))]


# --- explainability: why things happened -------------------------------------

MOMENTUM_WINDOW = 15  # minutes per window
FINAL_THIRD_X = 67  # x >= this is the attacking third (x runs from a team's own goal to the one it attacks)
CONTROL_TILT = 60.0  # field tilt (%) at which a team "controls" a window
PITCH_LENGTH_M, PITCH_WIDTH_M = 105, 68  # to turn 0-100 coordinates into metres


class MomentumWindow(TypedDict):
    start_minute: int
    end_minute: int  # inclusive; the last window runs to the final whistle
    possession: dict[Team, float]  # share of passes (%)
    field_tilt: dict[Team, float]  # share of passes made in the attacking third (%)
    shots: dict[Team, int]
    goals: list[int]  # event_ids of goals in this window
    possession_changes: int  # how often the ball changed hands
    control: str  # "Home", "Away" or "even": who had field tilt >= CONTROL_TILT
    tempo: str  # "frantic", "steady" or "normal": possession changes per minute vs the match average (±10%)


def momentum(match: Match) -> list[MomentumWindow]:
    """The match in 15-minute windows: who controlled the play, and how frantic it was.

    Control comes from field tilt (who made more passes in the attacking third). Tempo compares
    the possession changes per minute with this match's own average: > 1.1x is "frantic",
    < 0.9x is "steady".
    """
    if not match.events:
        return []
    last = match.events[-1].minute
    starts = list(range(0, last + 1, MOMENTUM_WINDOW))
    if len(starts) > 1 and last - starts[-1] < MOMENTUM_WINDOW // 3:
        starts.pop()  # a few stoppage-time minutes join the last full window
    match_rate = len(_possessions(match)) / (last + 1)
    windows: list[MomentumWindow] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] - 1 if i + 1 < len(starts) else last
        events = [e for e in match.events if start <= e.minute <= end]
        passes = {t: [e for e in events if e.team == t and e.type == "pass"] for t in TEAMS}
        total = sum(len(p) for p in passes.values())
        final_third = {t: sum(e.x >= FINAL_THIRD_X for e in passes[t]) for t in TEAMS}
        tilt_total = sum(final_third.values())
        tilt = {t: _percent(final_third[t], tilt_total) for t in TEAMS}
        changes = len({e.possession_id for e in events}) - 1
        rate = changes / (end - start + 1)
        windows.append(
            {
                "start_minute": start,
                "end_minute": end,
                "possession": {t: _percent(len(passes[t]), total) for t in TEAMS},
                "field_tilt": tilt,
                "shots": {t: sum(e.team == t and e.type == "shot" for e in events) for t in TEAMS},
                "goals": [e.event_id for e in events if e.type == "shot" and e.outcome == "goal"],
                "possession_changes": max(changes, 0),
                "control": next((t for t in TEAMS if tilt[t] >= CONTROL_TILT), "even"),
                "tempo": "frantic" if rate > 1.1 * match_rate else "steady" if rate < 0.9 * match_rate else "normal",
            }
        )
    return windows


class PressingStats(TypedDict):
    ball_wins: int  # tackles and interceptions won
    high: int  # won in the attacking third (x >= FINAL_THIRD_X)
    middle: int
    deep: int  # won in the defensive third (x < 33)
    high_win_shots: int  # possessions started by a high win that ended in a shot
    high_win_goals: int
    high_win_event_ids: list[int]


def pressing(match: Match) -> dict[Team, PressingStats]:
    """Where each team won the ball back, and what its high ball wins led to."""
    result: dict[Team, PressingStats] = {}
    possessions = _possessions(match)
    for team in TEAMS:
        wins = [e for e in match.events if e.team == team and e.type in ("tackle", "interception") and e.outcome == "won"]
        high = [e for e in wins if e.x >= FINAL_THIRD_X]
        high_ids = {e.event_id for e in high}
        led_to = [p[-1] for p in possessions if p[0].event_id in high_ids and p[-1].type == "shot"]
        result[team] = {
            "ball_wins": len(wins),
            "high": len(high),
            "middle": sum(33 <= e.x < FINAL_THIRD_X for e in wins),
            "deep": sum(e.x < 33 for e in wins),
            "high_win_shots": len(led_to),
            "high_win_goals": sum(e.outcome == "goal" for e in led_to),
            "high_win_event_ids": [e.event_id for e in high],
        }
    return result


class PassQualityStats(TypedDict):
    passes_measured: int  # passes whose end point is known (the next event)
    average_distance_m: float
    long_passes: int  # 30 m or more
    long_pass_accuracy: float
    progressive_passes: int  # moved the ball at least 15 m towards the opponent's goal
    average_difficulty: float  # 1 (easy) to 5 (hard), see pass_difficulty
    hard_passes: int  # difficulty 4 or 5
    hard_pass_accuracy: float


def _end_point(passer: Event, next_event: Event) -> tuple[float, float]:
    """Where a pass ended, in the passer's coordinates (the receiver or the player who stopped it)."""
    if next_event.team == passer.team:
        return next_event.x, next_event.y
    return 100 - next_event.x, 100 - next_event.y  # the other team measures from the other goal


def pass_difficulty(distance_m: float, forward_m: float, end_x: float) -> int:
    """A 1-5 difficulty rating: longer, more forward, and into the attacking third is harder.

    1 + up to 2 for distance (one per 20 m) + 1 if it gains 15 m or more + 1 if it ends in the attacking third.
    """
    return 1 + min(2, int(distance_m // 20)) + (forward_m >= 15) + (end_x >= FINAL_THIRD_X)


def pass_quality(match: Match) -> dict[Team, PassQualityStats]:
    """Pass distance, long and progressive passes, and a difficulty rating per team."""
    measured: dict[Team, list[tuple[float, float, int, bool]]] = {t: [] for t in TEAMS}
    for passer, nxt in zip(match.events, match.events[1:]):
        if passer.type != "pass" or nxt.possession_id not in (passer.possession_id, passer.possession_id + 1):
            continue
        end_x, end_y = _end_point(passer, nxt)
        dx = (end_x - passer.x) * PITCH_LENGTH_M / 100
        dy = (end_y - passer.y) * PITCH_WIDTH_M / 100
        distance = (dx**2 + dy**2) ** 0.5
        completed = passer.outcome == "complete"
        measured[passer.team].append((distance, dx, pass_difficulty(distance, dx, end_x), completed))
    result: dict[Team, PassQualityStats] = {}
    for team in TEAMS:
        rows = measured[team]
        long = [r for r in rows if r[0] >= 30]
        hard = [r for r in rows if r[2] >= 4]
        result[team] = {
            "passes_measured": len(rows),
            "average_distance_m": round(sum(r[0] for r in rows) / len(rows), 1) if rows else 0.0,
            "long_passes": len(long),
            "long_pass_accuracy": _percent(sum(r[3] for r in long), len(long)),
            "progressive_passes": sum(r[1] >= 15 for r in rows),
            "average_difficulty": round(sum(r[2] for r in rows) / len(rows), 2) if rows else 0.0,
            "hard_passes": len(hard),
            "hard_pass_accuracy": _percent(sum(r[3] for r in hard), len(hard)),
        }
    return result

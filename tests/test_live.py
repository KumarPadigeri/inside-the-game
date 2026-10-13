"""Tests for live mode: the minute-by-minute feed, moment detection and findings (no LLM calls)."""

import asyncio
from typing import Any

from inside_the_game import stats
from inside_the_game.generator import Match, generate_match
from inside_the_game.live import (
    Commentary,
    LiveCommentary,
    LiveMoment,
    collect,
    detect_moments,
    match_until,
    moment_findings,
    replay_commentator,
    run_live,
    tick,
)
from inside_the_game.narrator import RecapSentence

MATCH = generate_match(2)  # Northbridge FC 2-1 Oakhurst Albion: goals at 8', 14', 16'


def _play(commentator: Any = None) -> list[tuple[str, dict[str, Any]]]:
    async def run() -> list[tuple[str, dict[str, Any]]]:
        return [message async for message in run_live(MATCH, commentator, seconds_per_minute=0)]

    return asyncio.run(run())


def test_match_until_never_includes_later_events() -> None:
    so_far = match_until(MATCH, 15)
    assert so_far.events and all(e.minute <= 15 for e in so_far.events)
    assert so_far.score() == {"Home": 2, "Away": 0}
    assert len(MATCH.events) > len(so_far.events)  # the full match is untouched


def test_tick_reports_the_minute_and_running_stats() -> None:
    message = tick(match_until(MATCH, 15), 15)
    assert message["minute"] == 15
    assert message["score"] == {"Home": 2, "Away": 0}
    assert {e["minute"] for e in message["events"]} == {15}
    assert message["possession"]["Home"] + message["possession"]["Away"] == 100.0


def test_moments_are_detected_once_and_goals_are_not_also_counterattacks() -> None:
    seen: set[str] = set()
    first = detect_moments(match_until(MATCH, 16), seen)
    assert [m.kind for m in first] == ["goal", "goal", "goal"]
    assert [m.minute for m in first] == [8, 14, 16]
    assert detect_moments(match_until(MATCH, 16), seen) == []  # nothing new
    later = detect_moments(MATCH, seen)
    assert {m.kind for m in later} == {"counterattack"}
    goal_possessions = {g["buildup_event_ids"][0] for g in stats.goals(MATCH)}
    assert not any(m.event_ids[0] in goal_possessions for m in later)


def test_goal_findings_state_the_scorer_and_score_from_the_tools() -> None:
    so_far = match_until(MATCH, 16)
    goal = detect_moments(so_far, set())[2]
    report = moment_findings(so_far, goal, 16)
    first = report.findings[0]
    assert first.tool == "get_goals"
    assert "A6 scored for Oakhurst Albion in minute 16" in first.claim
    assert "Northbridge FC 2-1 Oakhurst Albion" in first.claim
    assert first.event_ids == goal.event_ids
    assert any("Earlier goals" in f.claim for f in report.findings)
    assert {f.tool for f in report.findings} >= {"get_match_info", "get_possession", "get_shots"}


def test_feed_runs_in_order_with_half_time_and_full_time() -> None:
    messages = _play()
    kinds = [kind for kind, _ in messages]
    assert kinds[0] == "tick" and kinds[-1] == "done"
    ticks = [data["minute"] for kind, data in messages if kind == "tick"]
    assert ticks == list(range(MATCH.events[-1].minute + 1))
    moments = [data["kind"] for kind, data in messages if kind == "moment"]
    assert moments.count("goal") == 3
    assert moments.index("half-time") < len(moments) - 1 and moments[-1] == "full-time"
    assert "commentary" not in kinds  # no commentator: stats only


def _line(moment: LiveMoment, text: str = "What a goal.") -> Commentary:
    sentence = RecapSentence(text=text, finding_ids=[1], event_ids=moment.event_ids, tools=["get_goals"])
    return Commentary(moment=moment, sentences=[sentence], stats={})


def test_commentary_is_sent_and_a_failing_comment_does_not_stop_the_match() -> None:
    async def commentator(match_so_far: Match, moment: LiveMoment) -> Commentary | None:
        if moment.kind == "counterattack":
            raise RuntimeError("model unavailable")
        if moment.kind == "goal":
            assert match_so_far.events[-1].minute <= moment.minute + 1  # it only sees the past
            return _line(moment)
        return None  # stay quiet

    messages = _play(commentator)
    lines = [data for kind, data in messages if kind == "commentary"]
    assert [line["moment"]["kind"] for line in lines] == ["goal", "goal", "goal"]
    assert messages[-1][0] == "done"


def test_saved_commentary_replays_and_collects_in_match_order() -> None:
    goals = detect_moments(MATCH, set())[:3]
    saved = collect([_line(goals[1]).model_dump(), _line(goals[0]).model_dump()], "fan", "es")
    assert [line.moment.minute for line in saved.lines] == [8, 14]
    assert saved.language == "es"

    messages = _play(replay_commentator(saved))
    replayed = [data["moment"]["key"] for kind, data in messages if kind == "commentary"]
    assert replayed == [goals[0].key, goals[1].key]
    assert LiveCommentary.model_validate(saved.model_dump()) == saved

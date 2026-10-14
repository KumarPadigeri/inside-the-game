"""Tests for the Analyst's tools and report checks (no LLM calls)."""

import pytest

from inside_the_game import stats
from inside_the_game.analyst import (
    TOOL_NAMES,
    AnalystReport,
    Finding,
    analyst_prompt,
    build_tools,
    normalize_tool_names,
    unknown_event_ids,
)
from inside_the_game.generator import generate_match


def test_tools_have_names_and_descriptions() -> None:
    tools = build_tools(generate_match(1))
    assert tuple(t.name for t in tools) == TOOL_NAMES[:-1]  # get_player_stats only in player focus mode
    assert all(t.description for t in tools)


def test_player_focus_adds_the_player_tool_and_asks_about_the_player() -> None:
    match = generate_match(5)
    by_name = {t.name: t for t in build_tools(match, player="H9")}
    assert tuple(by_name) == TOOL_NAMES
    assert by_name["get_player_stats"].func() == stats.player_stats(match, "H9")
    assert analyst_prompt() == "Analyse this match."
    assert "H9" in analyst_prompt("H9") and "get_player_stats" in analyst_prompt("H9")


def test_tools_return_the_stats_for_their_match() -> None:
    match = generate_match(5)
    by_name = {t.name: t for t in build_tools(match)}
    assert by_name["get_match_info"].func()["final_score"] == match.score()
    assert by_name["get_possession"].func() == stats.possession(match)
    assert by_name["get_goals"].func() == stats.goals(match)
    assert by_name["get_counterattacks"].func() == stats.counterattacks(match)


def test_unknown_event_ids_catches_made_up_evidence() -> None:
    match = generate_match(1)
    report = AnalystReport(
        findings=[
            Finding(claim="Real event.", tool="get_shots", event_ids=[1, 2]),
            Finding(claim="Invented event.", tool="get_goals", event_ids=[999_999]),
        ]
    )
    assert unknown_event_ids(report, match) == {999_999}


def test_normalize_tool_names_strips_namespaces() -> None:
    report = AnalystReport(findings=[Finding(claim="Goal.", tool="functions.get_goals", event_ids=[1])])
    assert normalize_tool_names(report).findings[0].tool == "get_goals"


def test_normalize_tool_names_rejects_unknown_tools() -> None:
    report = AnalystReport(findings=[Finding(claim="Made up.", tool="get_vibes", event_ids=[])])
    with pytest.raises(ValueError, match="unknown tool"):
        normalize_tool_names(report)

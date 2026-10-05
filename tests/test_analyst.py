"""Tests for the Analyst's tools and report checks (no LLM calls)."""

from inside_the_game import stats
from inside_the_game.analyst import AnalystReport, Finding, build_tools, unknown_event_ids
from inside_the_game.generator import generate_match


def test_tools_have_names_and_descriptions() -> None:
    tools = build_tools(generate_match(1))
    assert [t.name for t in tools] == [
        "get_match_info",
        "get_possession",
        "get_shots",
        "get_goals",
        "get_counterattacks",
    ]
    assert all(t.description for t in tools)


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

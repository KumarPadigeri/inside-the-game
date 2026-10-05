"""Analyst agent: turns tool-computed statistics into evidence-backed findings.

The agent never calculates anything. It calls the stats tools for one match
and reports findings, each citing the tool and event_ids that prove it.

Usage:
    python -m inside_the_game.analyst --seed 5
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from agent_framework import Agent, FunctionTool, tool
from agent_framework.foundry import FoundryChatClient
from pydantic import BaseModel, Field

from inside_the_game import stats
from inside_the_game.foundry import make_client
from inside_the_game.generator import Match, generate_match

INSTRUCTIONS = """\
You are a football match analyst. You receive no data directly: you must call
the tools to learn about the match. Call every tool before answering.

Rules:
- Never calculate, estimate or invent numbers. Use only values returned by tools.
- Report 5-8 findings, most important first: the result, how the goals came,
  turning points (lead changes, comebacks), counterattacks, shots, possession.
- Each finding is one short factual sentence. Refer to teams by their names
  and to players by their ids (e.g. H9).
- For every finding, give the tool that proves it.
- event_ids point to specific moments. Cite them only for findings about
  particular goals, counterattacks or shots, copied exactly from the tool
  result; never make them up. For totals, counts and percentages (the final
  score, shot totals, possession) cite an empty list: the tool result itself
  is the evidence.
"""


class Finding(BaseModel):
    claim: str = Field(description="One short factual sentence about the match.")
    tool: str = Field(description="Name of the tool whose result proves the claim.")
    event_ids: list[int] = Field(description="event_ids copied from that tool's result.")


class AnalystReport(BaseModel):
    findings: list[Finding]


def build_tools(match: Match) -> list[FunctionTool]:
    """Wrap the stats functions as agent tools bound to one match."""

    def get_match_info() -> dict[str, Any]:
        """Team names (Home and Away) and the final score."""
        return {
            "home_team": match.home_team,
            "away_team": match.away_team,
            "final_score": match.score(),
        }

    def get_possession() -> dict[str, Any]:
        """Possession per team as a share of all passes, with passes attempted, passes completed and pass accuracy (%)."""
        return dict(stats.possession(match))

    def get_shots() -> dict[str, Any]:
        """Shots per team: total, on target, goals, saved, missed, blocked, and the shot event_ids."""
        return dict(stats.shots(match))

    def get_goals() -> list[dict[str, Any]]:
        """Every goal in order: minute, team, scorer, score after the goal, and build-up event_ids."""
        return [dict(goal) for goal in stats.goals(match)]

    def get_counterattacks() -> list[dict[str, Any]]:
        """Counterattacks: ball won in own half, then a shot within a few passes. Includes event_ids."""
        return [dict(counter) for counter in stats.counterattacks(match)]

    return [tool(f) for f in (get_match_info, get_possession, get_shots, get_goals, get_counterattacks)]


def make_analyst(match: Match, client: FoundryChatClient | None = None) -> Agent:
    """Create the Analyst agent for one match."""
    return Agent(
        client=client or make_client(),
        name="Analyst",
        instructions=INSTRUCTIONS,
        tools=build_tools(match),
        default_options={"response_format": AnalystReport},
    )


TOOL_NAMES = ("get_match_info", "get_possession", "get_shots", "get_goals", "get_counterattacks")


def normalize_tool_names(report: AnalystReport) -> AnalystReport:
    """Strip namespaces the model sometimes adds ("functions.get_goals" -> "get_goals").

    Raises ValueError if a finding cites a tool that does not exist.
    """
    findings = []
    for finding in report.findings:
        name = finding.tool.rsplit(".", 1)[-1]
        if name not in TOOL_NAMES:
            raise ValueError(f"Analyst cited an unknown tool {finding.tool!r}: {finding.claim!r}")
        findings.append(finding.model_copy(update={"tool": name}))
    return AnalystReport(findings=findings)


def unknown_event_ids(report: AnalystReport, match: Match) -> set[int]:
    """event_ids cited in the report that do not exist in the match (should be empty)."""
    known = {e.event_id for e in match.events}
    return {i for finding in report.findings for i in finding.event_ids} - known


async def analyse(match: Match) -> AnalystReport:
    """Run the Analyst on a match and return its validated report."""
    response = await make_analyst(match).run("Analyse this match.")
    report = response.value
    if report is None:
        raise ValueError(f"Analyst returned no structured report: {response.text!r}")
    report = normalize_tool_names(report)
    bad = unknown_event_ids(report, match)
    if bad:
        raise ValueError(f"Analyst cited event_ids that do not exist: {sorted(bad)}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Analyst agent on a synthetic match.")
    parser.add_argument("--seed", type=int, default=1, help="which synthetic match to analyse")
    args = parser.parse_args()

    match = generate_match(args.seed)
    score = match.score()
    print(f"{match.home_team} {score['Home']}-{score['Away']} {match.away_team}\n")
    report = asyncio.run(analyse(match))
    for finding in report.findings:
        print(f"- {finding.claim}\n    [{finding.tool}] events {finding.event_ids}")


if __name__ == "__main__":
    main()

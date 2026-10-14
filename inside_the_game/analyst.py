"""Analyst agent: turns tool-computed statistics into evidence-backed findings.

The agent never calculates anything. It calls the stats tools for one match
and reports findings, each citing the tool and event_ids that prove it.

When ANALYST_MCP_URL is set (the API sets it to its own /mcp), the tools come
from the MCP server; if that fails, the Analyst falls back to the same tools
in-process, so a recap never fails because of MCP.

Usage:
    python -m inside_the_game.analyst --seed 5
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Any

from agent_framework import Agent, AgentResponse, FunctionTool, MCPStreamableHTTPTool, tool
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
- Report 6-9 findings, most important first: the result, how the goals came,
  turning points (lead changes, comebacks), counterattacks, shots, possession.
- Explain WHY, not only what: use get_momentum for who controlled which period
  and when the game turned or got frantic, get_pressing for where the ball was
  won back and what high ball wins led to, and get_pass_quality for how each
  team passed. Include at least two such "why" findings.
- Each finding is one short factual sentence. Refer to teams by their names
  and to players by their ids (e.g. H9).
- Describe pitch positions in words ("in its own half", "high up the pitch"),
  never as coordinates (x, y), and never mention internal ids or field names.
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


def build_tools(match: Match, player: str | None = None) -> list[FunctionTool]:
    """Wrap the stats functions as agent tools bound to one match.

    With `player` (player focus mode), add get_player_stats for that player.
    """

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

    def get_player_stats() -> dict[str, Any]:
        """The followed player's match: passing, shots, goals, tackles and interceptions won, the
        teammates' goals and the counterattacks they took part in, and the event_ids of their key moments."""
        assert player is not None
        return dict(stats.player_stats(match, player))

    def get_momentum() -> list[dict[str, Any]]:
        """The match in 15-minute windows: possession, field tilt (share of attacking-third passes), shots,
        goal event_ids, possession changes, and code-computed labels: control (team with field tilt >= 60%,
        else "even") and tempo ("frantic" / "steady" / "normal" vs this match's average rate of possession changes)."""
        return [dict(window) for window in stats.momentum(match)]

    def get_pressing() -> dict[str, Any]:
        """Where each team won the ball (tackles and interceptions): high (attacking third), middle, deep, and how
        many high ball wins led to a shot or a goal, with their event_ids."""
        return dict(stats.pressing(match))

    def get_pass_quality() -> dict[str, Any]:
        """Passing quality per team: average pass distance (m), long passes (30 m+) and their accuracy,
        progressive passes (15 m+ forward), average difficulty (1-5) and hard-pass (4-5) accuracy."""
        return dict(stats.pass_quality(match))

    functions = [
        get_match_info,
        get_possession,
        get_shots,
        get_goals,
        get_counterattacks,
        get_momentum,
        get_pressing,
        get_pass_quality,
    ]
    if player:
        functions.append(get_player_stats)
    return [tool(f) for f in functions]


def make_analyst(match: Match, client: FoundryChatClient | None = None, player: str | None = None) -> Agent:
    """Create the Analyst agent for one match (and, in player focus mode, one player)."""
    return Agent(
        client=client or make_client(),
        name="Analyst",
        instructions=INSTRUCTIONS,
        tools=build_tools(match, player),
        default_options={"response_format": AnalystReport},
    )


TOOL_NAMES = (
    "get_match_info",
    "get_possession",
    "get_shots",
    "get_goals",
    "get_counterattacks",
    "get_momentum",
    "get_pressing",
    "get_pass_quality",
    "get_player_stats",
)


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


def analyst_prompt(player: str | None = None) -> str:
    """The request to the Analyst; in player focus mode it also asks about that player."""
    if not player:
        return "Analyse this match."
    return (
        f"Analyse this match for a reader who follows player {player}. Call get_player_stats too, and make "
        f"3-4 of your findings about {player} (goals, shots, passing, ball winning, the goals and "
        f"counterattacks {player} took part in), citing get_player_stats. Keep 3-4 findings about the match."
    )


def mcp_prompt(match: Match, player: str | None = None) -> str:
    """Over MCP the tools serve every match, so the Analyst must pass this match's id to each call."""
    return f"The match_id is {match.match_id}: pass it to every tool. {analyst_prompt(player)}"


async def analyse_over_mcp(match: Match, url: str, player: str | None = None) -> AgentResponse:
    """Run the Analyst with its tools from the MCP server at `url`."""
    allowed = [name for name in TOOL_NAMES if player or name != "get_player_stats"]
    async with MCPStreamableHTTPTool(name="stats", url=url, allowed_tools=allowed, load_prompts=False) as tools:
        agent = Agent(
            client=make_client(),
            name="Analyst",
            instructions=INSTRUCTIONS,
            tools=tools,
            default_options={"response_format": AnalystReport},
        )
        return await agent.run(mcp_prompt(match, player))


async def analyse(match: Match, player: str | None = None) -> AnalystReport:
    """Run the Analyst on a match and return its validated report."""
    url = os.environ.get("ANALYST_MCP_URL")
    response: AgentResponse | None = None
    if url:
        try:
            response = await analyse_over_mcp(match, url, player)
        except Exception as error:  # noqa: BLE001 - the in-process tools give the same numbers
            logging.warning("MCP tools at %s failed (%s); using the in-process tools", url, error)
    if response is None:
        response = await make_analyst(match, player=player).run(analyst_prompt(player))
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

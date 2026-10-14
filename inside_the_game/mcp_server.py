"""MCP server: the deterministic stats tools, served over the Model Context Protocol.

The same tools the Analyst uses (possession, shots, goals, counterattacks,
momentum, pressing, pass quality, player stats) are offered to any MCP client
at /mcp (streamable HTTP). Each tool takes a match_id. The API mounts it, and
in the recap workflow the Analyst agent calls its tools through it.

It's read-only and serves synthetic data only, so it needs no login.

Try it with any MCP client, e.g. in VS Code (GitHub Copilot agent mode):
    "mcp": {"servers": {"inside-the-game": {"type": "http", "url": "<api url>/mcp"}}}
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from inside_the_game.analyst import build_tools
from inside_the_game.generator import Match

SERVER_NAME = "inside-the-game-stats"

INSTRUCTIONS = """\
Deterministic statistics for synthetic football matches (no real teams or players).
Call list_matches to find a match_id, then any stats tool with it. Every number is
computed by code from the match events, and results carry the event_ids that prove them.
"""

MatchLoader = Callable[[str], Awaitable[Match | None]]
MatchLister = Callable[[], Awaitable[list[dict[str, Any]]]]


def build_mcp_server(load_match: MatchLoader, list_matches: MatchLister) -> FastMCP:
    """An MCP server whose tools read matches through the given functions (Cosmos DB, or fakes in tests)."""
    server = FastMCP(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        streamable_http_path="/mcp",
        stateless_http=True,  # every call stands alone: nothing to keep between requests
        json_response=True,
        # The server sits behind the API's own host name in Azure, not localhost.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def result(match_id: str, tool_name: str, player: str | None = None) -> Any:
        match = await load_match(match_id)
        if match is None:
            raise ValueError(f"No match {match_id!r}; call list_matches for the ids")
        tools = {t.name: t for t in build_tools(match, player)}
        return tools[tool_name].func()

    @server.tool(name="list_matches")
    async def list_all_matches() -> list[dict[str, Any]]:
        """Every synthetic match: match_id, team names and final score."""
        return [
            {k: m[k] for k in ("match_id", "home_team", "away_team", "score") if k in m} for m in await list_matches()
        ]

    @server.tool()
    async def get_match_info(match_id: str) -> dict[str, Any]:
        """Team names (Home and Away) and the final score."""
        return await result(match_id, "get_match_info")

    @server.tool()
    async def get_possession(match_id: str) -> dict[str, Any]:
        """Possession per team as a share of all passes, with passes attempted, completed and pass accuracy (%)."""
        return await result(match_id, "get_possession")

    @server.tool()
    async def get_shots(match_id: str) -> dict[str, Any]:
        """Shots per team: total, on target, goals, saved, missed, blocked, and the shot event_ids."""
        return await result(match_id, "get_shots")

    @server.tool()
    async def get_goals(match_id: str) -> list[dict[str, Any]]:
        """Every goal in order: minute, team, scorer, score after the goal, and build-up event_ids."""
        return await result(match_id, "get_goals")

    @server.tool()
    async def get_counterattacks(match_id: str) -> list[dict[str, Any]]:
        """Counterattacks: ball won in own half, then a shot within a few passes. Includes event_ids."""
        return await result(match_id, "get_counterattacks")

    @server.tool()
    async def get_momentum(match_id: str) -> list[dict[str, Any]]:
        """The match in 15-minute windows: possession, field tilt, shots, goals, possession changes, and
        code-computed labels: control (team with field tilt >= 60%, else "even") and tempo."""
        return await result(match_id, "get_momentum")

    @server.tool()
    async def get_pressing(match_id: str) -> dict[str, Any]:
        """Where each team won the ball (high / middle / deep) and what its high ball wins led to."""
        return await result(match_id, "get_pressing")

    @server.tool()
    async def get_pass_quality(match_id: str) -> dict[str, Any]:
        """Pass distance (m), long and progressive passes, average difficulty (1-5) and hard-pass accuracy."""
        return await result(match_id, "get_pass_quality")

    @server.tool()
    async def get_player_stats(match_id: str, player: str) -> dict[str, Any]:
        """One player's match (player id like H9 or A11): passing, shots, goals, tackles and interceptions won,
        and the goals and counterattacks they took part in."""
        return await result(match_id, "get_player_stats", player)

    return server

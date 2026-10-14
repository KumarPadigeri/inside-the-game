"""Tests for the MCP server (real MCP JSON-RPC over HTTP, fake store) and the Analyst's MCP fallback."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from inside_the_game import analyst, stats
from inside_the_game.analyst import AnalystReport, Finding
from inside_the_game.api import create_app
from tests.test_api import MATCH, FakeStore

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    response = client.post("/mcp", headers=HEADERS, content=json.dumps(body))
    assert response.status_code == 200, response.text
    return response.json()


def _call(client: TestClient, tool: str, **arguments: Any) -> dict[str, Any]:
    return _rpc(client, "tools/call", {"name": tool, "arguments": arguments})["result"]


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app(FakeStore())) as test_client:
        yield test_client


def test_server_lists_the_stats_tools(client: TestClient) -> None:
    info = _rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "test", "version": "1"}})
    assert info["result"]["serverInfo"]["name"] == "inside-the-game-stats"
    names = {t["name"] for t in _rpc(client, "tools/list")["result"]["tools"]}
    assert names == {"list_matches", *analyst.TOOL_NAMES}


def test_tools_return_the_same_numbers_as_the_stats_code(client: TestClient) -> None:
    goals = _call(client, "get_goals", match_id="match_005")
    assert not goals.get("isError")
    assert json.loads(goals["content"][0]["text"])["event_id"] == stats.goals(MATCH)[0]["event_id"]
    player = _call(client, "get_player_stats", match_id="match_005", player="H9")
    assert player["structuredContent"]["player"] == "H9"
    listed = _call(client, "list_matches")["structuredContent"]["result"]
    assert listed[0]["match_id"] == "match_005"


def test_unknown_match_is_a_tool_error(client: TestClient) -> None:
    result = _call(client, "get_shots", match_id="match_999")
    assert result["isError"] and "list_matches" in result["content"][0]["text"]


REPORT = AnalystReport(findings=[Finding(claim="Home won.", tool="get_match_info", event_ids=[])])


class FakeAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, prompt: str) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(value=REPORT, text="")


def test_analyst_uses_mcp_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    local = FakeAgent()
    seen: list[str] = []

    async def fake_mcp(match, url, player=None):  # type: ignore[no-untyped-def]
        seen.append(url)
        return SimpleNamespace(value=REPORT, text="")

    monkeypatch.setenv("ANALYST_MCP_URL", "http://127.0.0.1:8000/mcp")
    monkeypatch.setattr(analyst, "analyse_over_mcp", fake_mcp)
    monkeypatch.setattr(analyst, "make_analyst", lambda match, player=None: local)
    assert asyncio.run(analyst.analyse(MATCH)) == REPORT
    assert seen == ["http://127.0.0.1:8000/mcp"] and local.calls == 0


def test_analyst_falls_back_to_local_tools_when_mcp_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    local = FakeAgent()

    async def broken_mcp(match, url, player=None):  # type: ignore[no-untyped-def]
        raise ConnectionError("MCP server down")

    monkeypatch.setenv("ANALYST_MCP_URL", "http://127.0.0.1:8000/mcp")
    monkeypatch.setattr(analyst, "analyse_over_mcp", broken_mcp)
    monkeypatch.setattr(analyst, "make_analyst", lambda match, player=None: local)
    assert asyncio.run(analyst.analyse(MATCH)) == REPORT
    assert local.calls == 1


def test_mcp_prompt_names_the_match() -> None:
    assert "match_005" in analyst.mcp_prompt(MATCH)
    assert "H9" in analyst.mcp_prompt(MATCH, "H9")

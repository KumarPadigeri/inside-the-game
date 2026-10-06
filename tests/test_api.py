"""Tests for the HTTP API, with a fake store and a fake workflow (no Azure or LLM calls)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from inside_the_game import workflow
from inside_the_game.api import create_app
from inside_the_game.generator import Match, generate_match
from inside_the_game.narrator import Recap, RecapSentence, Style
from inside_the_game.verifier import VerifiedRecap
from inside_the_game.workflow import Progress

MATCH = generate_match(5)
SENTENCE = RecapSentence(text="Ashvale won.", finding_ids=[1], event_ids=[198], tools=["get_goals"])
RECAP = VerifiedRecap(
    recap=Recap(style="fan", headline=SENTENCE, sentences=[SENTENCE]), rewrites=0, rejections=[], removed=[]
)


class FakeStore:
    def __init__(self) -> None:
        self.recaps: dict[tuple[str, str], VerifiedRecap] = {}

    async def list_matches(self) -> list[dict[str, Any]]:
        return [{"match_id": MATCH.match_id, "home_team": MATCH.home_team, "away_team": MATCH.away_team}]

    async def get_match(self, match_id: str) -> Match | None:
        return MATCH if match_id == MATCH.match_id else None

    async def get_recap(self, match_id: str, style: Style) -> VerifiedRecap | None:
        return self.recaps.get((match_id, style))

    async def save_recap(self, match_id: str, result: VerifiedRecap) -> None:
        self.recaps[(match_id, result.recap.style)] = result


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(store: FakeStore) -> TestClient:
    with TestClient(create_app(store)) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_and_get_matches(client: TestClient) -> None:
    assert client.get("/api/matches").json()[0]["match_id"] == "match_005"
    match = client.get("/api/matches/match_005").json()
    assert match["score"] == {"Home": 3, "Away": 2}
    assert len(match["events"]) == len(MATCH.events)


def test_unknown_match_is_404(client: TestClient) -> None:
    assert client.get("/api/matches/match_999").status_code == 404


def test_missing_recap_is_404_and_bad_style_is_422(client: TestClient) -> None:
    assert client.get("/api/matches/match_005/recaps/fan").status_code == 404
    assert client.get("/api/matches/match_005/recaps/poetry").status_code == 422


def test_create_recap_streams_progress_then_saves(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_stream(match: Match, style: Style) -> AsyncIterator[Progress | VerifiedRecap]:
        yield Progress(step="analyst", status="started")
        yield Progress(step="analyst", status="finished")
        yield RECAP

    monkeypatch.setattr(workflow, "stream_recap", fake_stream)

    body = client.post("/api/matches/match_005/recaps/fan").text
    assert body.index("event: progress") < body.index("event: recap")
    assert '"step": "analyst"' in body
    assert store.recaps[("match_005", "fan")] == RECAP
    assert client.get("/api/matches/match_005/recaps/fan").json()["recap"]["headline"]["text"] == "Ashvale won."


def test_create_recap_reports_errors_in_the_stream(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_stream(match: Match, style: Style) -> AsyncIterator[Progress | VerifiedRecap]:
        yield Progress(step="analyst", status="started")
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(workflow, "stream_recap", failing_stream)

    body = client.post("/api/matches/match_005/recaps/fan").text
    assert "event: error" in body and "model unavailable" in body

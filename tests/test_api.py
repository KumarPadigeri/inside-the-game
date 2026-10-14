"""Tests for the HTTP API, with a fake store and a fake workflow (no Azure or LLM calls)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from inside_the_game import commentator, workflow
from inside_the_game.api import create_app
from inside_the_game.generator import Match, generate_match
from inside_the_game.live import Commentary, LiveCommentary, LiveMoment, detect_moments
from inside_the_game.narrator import Language, Recap, RecapSentence, Style
from inside_the_game.verifier import VerifiedRecap
from inside_the_game.workflow import Progress

MATCH = generate_match(5)
SENTENCE = RecapSentence(text="Ashvale won.", finding_ids=[1], event_ids=[198], tools=["get_goals"])
RECAP = VerifiedRecap(
    recap=Recap(style="fan", headline=SENTENCE, sentences=[SENTENCE]), rewrites=0, rejections=[], removed=[]
)


class FakeStore:
    def __init__(self) -> None:
        self.recaps: dict[tuple[str, str, str], VerifiedRecap] = {}
        self.commentary: dict[tuple[str, str, str], LiveCommentary] = {}

    async def list_matches(self) -> list[dict[str, Any]]:
        return [{"match_id": MATCH.match_id, "home_team": MATCH.home_team, "away_team": MATCH.away_team}]

    async def get_match(self, match_id: str) -> Match | None:
        return MATCH if match_id == MATCH.match_id else None

    async def get_recap(
        self, match_id: str, style: Style, language: Language = "en", focus: str = ""
    ) -> VerifiedRecap | None:
        return self.recaps.get((match_id, style, language + focus))

    async def save_recap(self, match_id: str, result: VerifiedRecap) -> None:
        self.recaps[(match_id, result.recap.style, result.recap.language + result.recap.focus)] = result

    async def get_commentary(
        self, match_id: str, style: Style, language: Language = "en", focus: str = ""
    ) -> LiveCommentary | None:
        return self.commentary.get((match_id, style, language + focus))

    async def save_commentary(self, match_id: str, commentary: LiveCommentary) -> None:
        self.commentary[(match_id, commentary.style, commentary.language + commentary.focus)] = commentary


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


def test_stats_are_the_tool_results(client: TestClient) -> None:
    stats = client.get("/api/matches/match_005/stats").json()
    assert set(stats) == {"get_match_info", "get_possession", "get_shots", "get_goals", "get_counterattacks"}
    assert stats["get_shots"]["Home"]["total"] == 16
    assert client.get("/api/matches/match_999/stats").status_code == 404


def test_unknown_match_is_404(client: TestClient) -> None:
    assert client.get("/api/matches/match_999").status_code == 404


def test_missing_recap_is_404_and_bad_style_is_422(client: TestClient) -> None:
    assert client.get("/api/matches/match_005/recaps/fan").status_code == 404
    assert client.get("/api/matches/match_005/recaps/poetry").status_code == 422
    assert client.get("/api/matches/match_005/recaps/fan?language=klingon").status_code == 422


def test_create_recap_streams_progress_then_saves(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_stream(match: Match, style: Style, language: Language, focus: str = "") -> AsyncIterator[Progress | VerifiedRecap]:
        yield Progress(step="analyst", status="started")
        yield Progress(step="analyst", status="finished")
        yield RECAP

    monkeypatch.setattr(workflow, "stream_recap", fake_stream)

    body = client.post("/api/matches/match_005/recaps/fan").text
    assert body.index("event: progress") < body.index("event: recap")
    assert '"step": "analyst"' in body
    assert store.recaps[("match_005", "fan", "en")] == RECAP
    assert client.get("/api/matches/match_005/recaps/fan").json()["recap"]["headline"]["text"] == "Ashvale won."


def test_language_reaches_the_workflow_and_picks_the_saved_recap(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    spanish = RECAP.model_copy(update={"recap": RECAP.recap.model_copy(update={"language": "es"})})
    asked: list[str] = []

    async def fake_stream(match: Match, style: Style, language: Language, focus: str = "") -> AsyncIterator[Progress | VerifiedRecap]:
        asked.append(language)
        yield spanish

    monkeypatch.setattr(workflow, "stream_recap", fake_stream)

    client.post("/api/matches/match_005/recaps/fan?language=es")
    assert asked == ["es"]
    assert client.get("/api/matches/match_005/recaps/fan?language=es").json()["recap"]["language"] == "es"
    assert client.get("/api/matches/match_005/recaps/fan").status_code == 404  # no English recap saved


def test_create_recap_reports_errors_in_the_stream(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_stream(match: Match, style: Style, language: Language, focus: str = "") -> AsyncIterator[Progress | VerifiedRecap]:
        yield Progress(step="analyst", status="started")
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(workflow, "stream_recap", failing_stream)

    body = client.post("/api/matches/match_005/recaps/fan").text
    assert "event: error" in body and "model unavailable" in body


def test_generating_needs_the_passcode_when_one_is_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_stream(match: Match, style: Style, language: Language, focus: str = "") -> AsyncIterator[Progress | VerifiedRecap]:
        yield RECAP

    monkeypatch.setattr(workflow, "stream_recap", fake_stream)
    monkeypatch.setenv("RECAP_PASSCODE", "open-sesame")
    url = "/api/matches/match_005/recaps/fan"
    assert client.post(url).status_code == 403
    assert client.post(url, headers={"X-Recap-Passcode": "wrong"}).status_code == 403
    response = client.post(url, headers={"X-Recap-Passcode": "open-sesame"})
    assert response.status_code == 200 and "event: recap" in response.text
    # Reading stays open to everyone.
    assert client.get("/api/matches/match_005").status_code == 200


def test_generating_is_disabled_in_azure_without_a_passcode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RECAP_PASSCODE", raising=False)
    monkeypatch.setenv("CONTAINER_APP_NAME", "inside-the-game-api")
    response = client.post("/api/matches/match_005/recaps/fan")
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


def _sse(body: str) -> list[str]:
    return [line.removeprefix("event: ").strip() for line in body.splitlines() if line.startswith("event: ")]


def _goal_line(moment: LiveMoment) -> Commentary:
    return Commentary(moment=moment, sentences=[SENTENCE], stats={})


def test_watching_live_is_free_and_streams_the_overlay_feed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECAP_PASSCODE", "open-sesame")  # not needed to watch
    body = client.get("/api/matches/match_005/live/fan?seconds_per_minute=0").text
    events = _sse(body)
    assert events[0] == "start" and events[-1] == "done"
    assert "tick" in events and "moment" in events
    assert '"commentary": "none"' in body and "event: commentary" not in body
    assert client.get("/api/matches/match_005/live/fan?seconds_per_minute=9").status_code == 422


def test_saved_commentary_is_replayed_live(client: TestClient, store: FakeStore) -> None:
    first_goal = detect_moments(MATCH, set())[0]
    store.commentary[("match_005", "fan", "en")] = LiveCommentary(style="fan", lines=[_goal_line(first_goal)])
    body = client.get("/api/matches/match_005/live/fan?seconds_per_minute=0").text
    assert '"commentary": "saved"' in body
    assert _sse(body).count("commentary") == 1
    assert client.get("/api/matches/match_005/live/fan?language=es&seconds_per_minute=0").text.count(
        "event: commentary"
    ) == 0  # no Spanish run saved


def test_live_commentary_needs_the_passcode_and_is_saved(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_make_commentator(style: Style, language: Language, focus: str = ""):  # type: ignore[no-untyped-def]
        async def commentate(match_so_far: Match, moment: LiveMoment) -> Commentary | None:
            return _goal_line(moment) if moment.kind == "goal" else None

        return commentate

    monkeypatch.setattr(commentator, "make_commentator", fake_make_commentator)
    monkeypatch.setenv("RECAP_PASSCODE", "open-sesame")
    url = "/api/matches/match_005/live/fan?language=es&seconds_per_minute=0"
    assert client.post(url).status_code == 403
    body = client.post(url, headers={"X-Recap-Passcode": "open-sesame"}).text
    assert _sse(body).count("commentary") == MATCH.score()["Home"] + MATCH.score()["Away"]
    saved = store.commentary[("match_005", "fan", "es")]
    assert [line.moment.kind for line in saved.lines] == ["goal"] * 5


def test_personalized_recaps_are_validated_and_kept_apart(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    async def fake_stream(match: Match, style: Style, language: Language, focus: str = "") -> AsyncIterator[Progress | VerifiedRecap]:
        asked.append(focus)
        yield RECAP.model_copy(update={"recap": RECAP.recap.model_copy(update={"focus": focus})})

    monkeypatch.setattr(workflow, "stream_recap", fake_stream)
    url = "/api/matches/match_005/recaps/fan"
    assert client.post(f"{url}?focus=Away").status_code == 200
    assert client.post(f"{url}?focus=H9").status_code == 200
    assert asked == ["Away", "H9"]
    assert client.get(f"{url}?focus=Away").json()["recap"]["focus"] == "Away"
    assert client.get(url).status_code == 404  # the neutral recap is a different one
    assert client.post(f"{url}?focus=H99").status_code == 422  # did not play
    assert client.get(f"{url}?focus=everyone").status_code == 422
    live_url = "/api/matches/match_005/live/fan?seconds_per_minute=0"
    assert client.get(f"{live_url}&focus=H9").status_code == 422  # live personalizes by club only
    assert '"focus": "Home"' in client.get(f"{live_url}&focus=Home").text


def test_stats_include_the_followed_player() -> None:
    with TestClient(create_app(FakeStore())) as client:
        stats = client.get("/api/matches/match_005/stats?player=H9").json()
        assert stats["get_player_stats"]["player"] == "H9"
        assert "get_player_stats" not in client.get("/api/matches/match_005/stats").json()
        assert client.get("/api/matches/match_005/stats?player=H99").status_code == 422

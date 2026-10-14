"""HTTP API for the React UI (FastAPI).

    GET  /api/health
    GET  /api/matches                              match summaries
    GET  /api/matches/{match_id}                   one match with all its events
    GET  /api/matches/{match_id}/stats             tool results (the evidence behind totals)
    GET  /api/matches/{match_id}/recaps/{style}    a saved verified recap
    POST /api/matches/{match_id}/recaps/{style}    run the agents; streams progress
                                                   (Server-Sent Events), then saves
    GET  /api/matches/{match_id}/live/{style}      play the match live (SSE overlay feed), replaying
                                                   saved commentary if there is any; free, no AI
    POST /api/matches/{match_id}/live/{style}      play it live with fresh commentary from the
                                                   Commentator and Verifier agents, then save it
    Recap and live endpoints take ?language=en|es|fr|pt|hi (default en) and ?focus= to personalize:
    Home / Away (the club the reader supports) or, for recaps, a player id (player focus mode).
    Live ones also take ?seconds_per_minute= (default 1).

    /mcp    the stats tools as an MCP server (streamable HTTP), see mcp_server.py.
            The Analyst calls its tools through it when the API runs a recap.

Generating calls the AI models (it costs credit), so the POST needs the
X-Recap-Passcode header to match RECAP_PASSCODE. Reading is open to everyone.
Without RECAP_PASSCODE, generating is allowed locally and disabled in Azure.

Usage:
    uvicorn inside_the_game.api:app --reload
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, Protocol

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sse_starlette.sse import EventSourceResponse

from inside_the_game import live, workflow
from inside_the_game.analyst import build_tools
from inside_the_game.foundry import running_in_azure
from inside_the_game.generator import Match
from inside_the_game.live import LiveCommentary
from inside_the_game.mcp_server import build_mcp_server
from inside_the_game.narrator import FOCUS_PATTERN, Language, Style, focus_player
from inside_the_game.verifier import VerifiedRecap


PASSCODE_HEADER = "X-Recap-Passcode"


def check_passcode(given: str | None) -> None:
    """Allow generating only with the right passcode (see module docstring)."""
    expected = os.environ.get("RECAP_PASSCODE")
    if not expected:
        if running_in_azure():
            raise HTTPException(status_code=403, detail="Generating recaps is disabled on this server")
        return  # local development
    if not given or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Generating recaps needs the demo passcode")


class MatchStore(Protocol):
    """What the API needs from storage (the real Store, or a fake in tests)."""

    async def list_matches(self) -> list[dict[str, Any]]: ...
    async def get_match(self, match_id: str) -> Match | None: ...
    async def get_recap(
        self, match_id: str, style: Style, language: Language = "en", focus: str = ""
    ) -> VerifiedRecap | None: ...
    async def save_recap(self, match_id: str, result: VerifiedRecap) -> None: ...
    async def get_commentary(
        self, match_id: str, style: Style, language: Language = "en", focus: str = ""
    ) -> LiveCommentary | None: ...
    async def save_commentary(self, match_id: str, commentary: LiveCommentary) -> None: ...


def create_app(store: MatchStore | None = None) -> FastAPI:
    """Build the app. With no store given, it opens the Cosmos DB Store on startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with mcp.session_manager.run():
            if store is not None:
                app.state.store = store
                yield
                return
            from inside_the_game.store import Store  # needs COSMOS_* settings
            from inside_the_game.tracing import setup_tracing

            await setup_tracing()  # on in Azure; locally with TRACING=1
            # The Analyst reaches its tools through this server's own /mcp (see analyst.ANALYST_MCP_URL).
            os.environ.setdefault("ANALYST_MCP_URL", "http://127.0.0.1:8000/mcp")
            async with Store() as cosmos:
                app.state.store = cosmos
                yield

    app = FastAPI(title="Inside the Game", lifespan=lifespan)
    # Trace incoming requests, so each recap run hangs under the POST that started it.
    # (Tracing is configured later, at startup; until then this records nothing.)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/api/health")

    # The stats tools as an MCP server, reading matches from the same store.
    async def mcp_load_match(match_id: str) -> Match | None:
        return await app.state.store.get_match(match_id)

    async def mcp_list_matches() -> list[dict[str, Any]]:
        return await app.state.store.list_matches()

    mcp = build_mcp_server(mcp_load_match, mcp_list_matches)
    app.router.routes.extend(mcp.streamable_http_app().routes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    RecapFocus = Query(default="", pattern=FOCUS_PATTERN, description="Home / Away, or a player id like H9")
    LiveFocus = Query(default="", pattern=r"^(Home|Away)?$", description="The club the commentary supports")

    def get_store(request: Request) -> MatchStore:
        return request.app.state.store

    def check_player(match: Match, focus: str) -> None:
        """Player focus needs a player who actually played in this match."""
        player = focus_player(focus)
        if player and not any(e.player == player for e in match.events):
            raise HTTPException(status_code=422, detail=f"Player {player} did not play in {match.match_id}")

    async def require_match(request: Request, match_id: str) -> Match:
        match = await get_store(request).get_match(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail=f"No match {match_id!r}")
        return match

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/matches")
    async def list_matches(request: Request) -> list[dict[str, Any]]:
        return await get_store(request).list_matches()

    @app.get("/api/matches/{match_id}")
    async def get_match(request: Request, match_id: str) -> dict[str, Any]:
        match = await require_match(request, match_id)
        return {**match.to_dict(), "score": match.score()}

    @app.get("/api/matches/{match_id}/stats")
    async def get_stats(request: Request, match_id: str, player: str | None = None) -> dict[str, Any]:
        """The same tool results the agents saw, keyed by tool name (with ?player=, get_player_stats too)."""
        match = await require_match(request, match_id)
        if player:
            check_player(match, player)
        return {t.name: t.func() for t in build_tools(match, player)}

    @app.get("/api/matches/{match_id}/recaps/{style}")
    async def get_recap(
        request: Request, match_id: str, style: Style, language: Language = "en", focus: str = RecapFocus
    ) -> VerifiedRecap:
        recap = await get_store(request).get_recap(match_id, style, language, focus)
        if recap is None:
            raise HTTPException(status_code=404, detail=f"No {style} recap in {language!r} for {match_id!r} yet")
        return recap

    @app.post("/api/matches/{match_id}/recaps/{style}")
    async def create_recap(
        request: Request,
        match_id: str,
        style: Style,
        language: Language = "en",
        focus: str = RecapFocus,
        passcode: str | None = Header(default=None, alias=PASSCODE_HEADER),
    ) -> EventSourceResponse:
        check_passcode(passcode)
        match = await require_match(request, match_id)
        check_player(match, focus)
        store_ = get_store(request)

        async def events() -> AsyncIterator[dict[str, str]]:
            try:
                async for item in workflow.stream_recap(match, style, language, focus):
                    if isinstance(item, VerifiedRecap):
                        await store_.save_recap(match_id, item)
                        yield {"event": "recap", "data": item.model_dump_json()}
                    else:
                        yield {"event": "progress", "data": json.dumps(asdict(item))}
            except Exception as error:  # noqa: BLE001 - report any failure to the UI
                logging.exception("Recap failed for %s (%s, %s)", match_id, style, language)
                yield {"event": "error", "data": json.dumps({"detail": str(error)})}

        return EventSourceResponse(events())

    SecondsPerMinute = Query(default=1.0, ge=0, le=5, description="Playback speed: seconds per match minute")

    def live_events(
        match: Match,
        commentator: live.Commentator | None,
        seconds_per_minute: float,
        start: dict[str, Any],
        on_done: Callable[[list[dict[str, Any]]], Awaitable[None]] | None = None,
    ) -> EventSourceResponse:
        """Stream the live feed as Server-Sent Events: start, then tick / moment / commentary, then done."""

        async def events() -> AsyncIterator[dict[str, str]]:
            yield {"event": "start", "data": json.dumps(start)}
            lines: list[dict[str, Any]] = []
            try:
                async for kind, data in live.run_live(match, commentator, seconds_per_minute):
                    if kind == "commentary":
                        lines.append(data)
                    if kind == "done" and on_done is not None:
                        await on_done(lines)
                    yield {"event": kind, "data": json.dumps(data)}
            except Exception as error:  # noqa: BLE001 - report any failure to the UI
                logging.exception("Live feed failed for %s", match.match_id)
                yield {"event": "error", "data": json.dumps({"detail": str(error)})}

        return EventSourceResponse(events())

    @app.get("/api/matches/{match_id}/live/{style}")
    async def watch_live(
        request: Request,
        match_id: str,
        style: Style,
        language: Language = "en",
        focus: str = LiveFocus,
        seconds_per_minute: float = SecondsPerMinute,
    ) -> EventSourceResponse:
        """Free for everyone: live stats from code, plus saved commentary if this match has some."""
        match = await require_match(request, match_id)
        saved = await get_store(request).get_commentary(match_id, style, language, focus)
        commentator = live.replay_commentator(saved) if saved else None
        start = {
            "match_id": match_id,
            "style": style,
            "language": language,
            "focus": focus,
            "commentary": "saved" if saved else "none",
        }
        return live_events(match, commentator, seconds_per_minute, start)

    @app.post("/api/matches/{match_id}/live/{style}")
    async def generate_live(
        request: Request,
        match_id: str,
        style: Style,
        language: Language = "en",
        focus: str = LiveFocus,
        seconds_per_minute: float = SecondsPerMinute,
        passcode: str | None = Header(default=None, alias=PASSCODE_HEADER),
    ) -> EventSourceResponse:
        """Live with fresh commentary from the agents (needs the passcode); saved for free replays."""
        check_passcode(passcode)
        match = await require_match(request, match_id)
        store_ = get_store(request)
        from inside_the_game.commentator import make_commentator  # loads the agents only when needed

        async def save(lines: list[dict[str, Any]]) -> None:
            if lines:
                await store_.save_commentary(match_id, live.collect(lines, style, language, focus))

        start = {"match_id": match_id, "style": style, "language": language, "focus": focus, "commentary": "live"}
        return live_events(match, make_commentator(style, language, focus), seconds_per_minute, start, on_done=save)

    return app


app = create_app()

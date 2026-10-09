"""HTTP API for the React UI (FastAPI).

    GET  /api/health
    GET  /api/matches                              match summaries
    GET  /api/matches/{match_id}                   one match with all its events
    GET  /api/matches/{match_id}/stats             tool results (the evidence behind totals)
    GET  /api/matches/{match_id}/recaps/{style}    a saved verified recap
    POST /api/matches/{match_id}/recaps/{style}    run the agents; streams progress
                                                   (Server-Sent Events), then saves

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
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, Protocol

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from inside_the_game import workflow
from inside_the_game.analyst import build_tools
from inside_the_game.foundry import running_in_azure
from inside_the_game.generator import Match
from inside_the_game.narrator import Style
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
    async def get_recap(self, match_id: str, style: Style) -> VerifiedRecap | None: ...
    async def save_recap(self, match_id: str, result: VerifiedRecap) -> None: ...


def create_app(store: MatchStore | None = None) -> FastAPI:
    """Build the app. With no store given, it opens the Cosmos DB Store on startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        if store is not None:
            app.state.store = store
            yield
            return
        from inside_the_game.store import Store  # needs COSMOS_* settings

        async with Store() as cosmos:
            app.state.store = cosmos
            yield

    app = FastAPI(title="Inside the Game", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def get_store(request: Request) -> MatchStore:
        return request.app.state.store

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
    async def get_stats(request: Request, match_id: str) -> dict[str, Any]:
        """The same tool results the agents saw, keyed by tool name."""
        match = await require_match(request, match_id)
        return {t.name: t.func() for t in build_tools(match)}

    @app.get("/api/matches/{match_id}/recaps/{style}")
    async def get_recap(request: Request, match_id: str, style: Style) -> VerifiedRecap:
        recap = await get_store(request).get_recap(match_id, style)
        if recap is None:
            raise HTTPException(status_code=404, detail=f"No {style} recap for {match_id!r} yet")
        return recap

    @app.post("/api/matches/{match_id}/recaps/{style}")
    async def create_recap(
        request: Request,
        match_id: str,
        style: Style,
        passcode: str | None = Header(default=None, alias=PASSCODE_HEADER),
    ) -> EventSourceResponse:
        check_passcode(passcode)
        match = await require_match(request, match_id)
        store_ = get_store(request)

        async def events() -> AsyncIterator[dict[str, str]]:
            try:
                async for item in workflow.stream_recap(match, style):
                    if isinstance(item, VerifiedRecap):
                        await store_.save_recap(match_id, item)
                        yield {"event": "recap", "data": item.model_dump_json()}
                    else:
                        yield {"event": "progress", "data": json.dumps(asdict(item))}
            except Exception as error:  # noqa: BLE001 - report any failure to the UI
                logging.exception("Recap failed for %s (%s)", match_id, style)
                yield {"event": "error", "data": json.dumps({"detail": str(error)})}

        return EventSourceResponse(events())

    return app


app = create_app()

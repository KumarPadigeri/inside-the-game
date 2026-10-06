"""Azure Cosmos DB storage for matches and verified recaps.

Containers (all partitioned by /match_id):
    matches - one document per synthetic match, events included
    recaps  - one document per (match, style) verified recap
    moments - goals and counterattacks with embedding vectors, for vector search

Auth uses Entra ID (your `az login` locally, the managed identity in Azure);
key-based access is disabled on the account, so there are no secrets to manage.

Usage:
    python -m inside_the_game.store --count 5 --seed 1   # upload generated matches
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from dotenv import load_dotenv

from inside_the_game.foundry import make_async_credential
from inside_the_game.generator import Match, generate_match
from inside_the_game.moments import Moment
from inside_the_game.narrator import Style
from inside_the_game.verifier import VerifiedRecap

# --- document conversion (pure, no Azure) ---------------------------------


def match_to_doc(match: Match) -> dict[str, Any]:
    """A match as a Cosmos document. The final score is stored for cheap listing."""
    return {"id": match.match_id, **match.to_dict(), "score": match.score()}


def doc_to_match(doc: dict[str, Any]) -> Match:
    return Match.from_dict(doc)


def recap_id(match_id: str, style: Style) -> str:
    return f"{match_id}-{style}"


def recap_to_doc(match_id: str, result: VerifiedRecap) -> dict[str, Any]:
    """A verified recap as a Cosmos document, one per match and style."""
    return {
        "id": recap_id(match_id, result.recap.style),
        "match_id": match_id,
        "style": result.recap.style,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **result.model_dump(),
    }


def doc_to_recap(doc: dict[str, Any]) -> VerifiedRecap:
    return VerifiedRecap.model_validate(doc)


def moment_to_doc(moment: Moment, embedding: list[float]) -> dict[str, Any]:
    return {"id": moment.moment_id, **moment.model_dump(), "embedding": embedding}


# Moment fields returned by queries (everything except the large embedding).
_MOMENT_FIELDS = ", ".join(f"c.{name}" for name in Moment.model_fields)


# --- Cosmos DB access -------------------------------------------------------


class Store:
    """Async access to the matches and recaps containers.

    Use as `async with Store() as store: ...` so connections are closed.
    """

    def __init__(self, endpoint: str | None = None, database: str | None = None) -> None:
        load_dotenv()
        self._credential = make_async_credential()
        self._client = CosmosClient(endpoint or os.environ["COSMOS_ENDPOINT"], credential=self._credential)
        db = self._client.get_database_client(database or os.environ["COSMOS_DATABASE"])
        self.matches: ContainerProxy = db.get_container_client("matches")
        self.recaps: ContainerProxy = db.get_container_client("recaps")
        self.moments: ContainerProxy = db.get_container_client("moments")

    async def __aenter__(self) -> Store:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.close()
        await self._credential.close()

    async def save_match(self, match: Match) -> None:
        await self.matches.upsert_item(match_to_doc(match))

    async def get_match(self, match_id: str) -> Match | None:
        try:
            return doc_to_match(await self.matches.read_item(match_id, partition_key=match_id))
        except CosmosResourceNotFoundError:
            return None

    async def list_matches(self) -> list[dict[str, Any]]:
        """Match summaries (no events), ordered by match_id."""
        query = "SELECT c.match_id, c.home_team, c.away_team, c.score FROM c ORDER BY c.match_id"
        return [item async for item in self.matches.query_items(query)]

    async def save_recap(self, match_id: str, result: VerifiedRecap) -> None:
        await self.recaps.upsert_item(recap_to_doc(match_id, result))

    async def get_recap(self, match_id: str, style: Style) -> VerifiedRecap | None:
        try:
            doc = await self.recaps.read_item(recap_id(match_id, style), partition_key=match_id)
            return doc_to_recap(doc)
        except CosmosResourceNotFoundError:
            return None

    async def save_moment(self, moment: Moment, embedding: list[float]) -> None:
        await self.moments.upsert_item(moment_to_doc(moment, embedding))

    async def get_moment(self, moment_id: str) -> Moment | None:
        match_id = moment_id.rsplit("-p", 1)[0]
        try:
            return Moment.model_validate(await self.moments.read_item(moment_id, partition_key=match_id))
        except CosmosResourceNotFoundError:
            return None

    async def similar_moments(self, moment_id: str, top_k: int = 3) -> list[dict[str, Any]]:
        """The top_k moments of the same kind from OTHER matches, closest to an indexed moment."""
        match_id = moment_id.rsplit("-p", 1)[0]
        source = await self.moments.read_item(moment_id, partition_key=match_id)
        return await self.similar_to(source["embedding"], kind=source["kind"], exclude_match_id=match_id, top_k=top_k)

    async def similar_to(
        self, vector: list[float], kind: str, exclude_match_id: str, top_k: int = 3
    ) -> list[dict[str, Any]]:
        """The top_k moments of this kind, from other matches, closest to a vector.

        The kind filter is exact; the vector search then ranks by how the play
        happened. Each result has the Moment fields plus "similarity" (cosine,
        1.0 = identical).
        """
        query = (
            f"SELECT TOP @k {_MOMENT_FIELDS}, VectorDistance(c.embedding, @vector) AS similarity "
            "FROM c WHERE c.match_id != @match_id AND c.kind = @kind "
            "ORDER BY VectorDistance(c.embedding, @vector)"
        )
        parameters: list[dict[str, Any]] = [
            {"name": "@k", "value": top_k},
            {"name": "@vector", "value": vector},
            {"name": "@match_id", "value": exclude_match_id},
            {"name": "@kind", "value": kind},
        ]
        return [item async for item in self.moments.query_items(query, parameters=parameters)]

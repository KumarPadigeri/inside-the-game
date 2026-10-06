"""Azure Cosmos DB storage for matches and verified recaps.

Containers (both partitioned by /match_id):
    matches - one document per synthetic match, events included
    recaps  - one document per (match, style) verified recap

Auth uses your `az login` via Entra ID; key-based access is disabled on the
account, so there are no secrets to manage.

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
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

from inside_the_game.generator import Match, generate_match
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


# --- Cosmos DB access -------------------------------------------------------


class Store:
    """Async access to the matches and recaps containers.

    Use as `async with Store() as store: ...` so connections are closed.
    """

    def __init__(self, endpoint: str | None = None, database: str | None = None) -> None:
        load_dotenv()
        self._credential = AzureCliCredential()
        self._client = CosmosClient(endpoint or os.environ["COSMOS_ENDPOINT"], credential=self._credential)
        db = self._client.get_database_client(database or os.environ["COSMOS_DATABASE"])
        self.matches: ContainerProxy = db.get_container_client("matches")
        self.recaps: ContainerProxy = db.get_container_client("recaps")

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


async def upload_matches(seeds: range) -> None:
    async with Store() as store:
        for seed in seeds:
            match = generate_match(seed)
            await store.save_match(match)
            score = match.score()
            print(f"saved {match.match_id}: {match.home_team} {score['Home']}-{score['Away']} {match.away_team}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload synthetic matches to Cosmos DB.")
    parser.add_argument("--count", type=int, default=5, help="number of matches")
    parser.add_argument("--seed", type=int, default=1, help="seed of the first match")
    args = parser.parse_args()
    asyncio.run(upload_matches(range(args.seed, args.seed + args.count)))


if __name__ == "__main__":
    main()

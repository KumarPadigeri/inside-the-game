"""Shared connections to Microsoft Foundry: the chat model (every agent) and the embedding model."""

import os

from agent_framework.foundry import FoundryChatClient, FoundryEmbeddingClient
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from dotenv import load_dotenv


def make_client() -> FoundryChatClient:
    """Create a chat client from FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL in .env.

    Auth reuses your `az login` session, so no API keys are needed.
    """
    load_dotenv()
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Turn texts into vectors with FOUNDRY_EMBEDDING_MODEL (one vector per text, same order)."""
    if not texts:
        return []
    load_dotenv()
    async with AsyncAzureCliCredential() as credential:
        client = FoundryEmbeddingClient(
            model=os.environ["FOUNDRY_EMBEDDING_MODEL"],
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
        )
        try:
            embeddings = await client.get_embeddings(texts)
        finally:
            await client.close()
    return [list(e.vector) for e in embeddings]

"""Shared Azure connections: credentials, the chat model (every agent) and the embedding model.

Credentials: locally we reuse your `az login`; inside Azure Container Apps
(where CONTAINER_APP_NAME is set) we use the app's managed identity. Either
way there are no keys or secrets.
"""

import os

from agent_framework.foundry import FoundryChatClient, FoundryEmbeddingClient
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity import AzureCliCredential, ManagedIdentityCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from azure.identity.aio import ManagedIdentityCredential as AsyncManagedIdentityCredential
from dotenv import load_dotenv


def running_in_azure() -> bool:
    """Azure Container Apps sets CONTAINER_APP_NAME in every container."""
    return "CONTAINER_APP_NAME" in os.environ


def make_credential() -> TokenCredential:
    """Managed identity in Azure, your `az login` locally."""
    return ManagedIdentityCredential() if running_in_azure() else AzureCliCredential()


def make_async_credential() -> AsyncTokenCredential:
    """Async version of make_credential(), for async SDK clients (Cosmos DB, embeddings)."""
    return AsyncManagedIdentityCredential() if running_in_azure() else AsyncAzureCliCredential()


def make_client() -> FoundryChatClient:
    """Create a chat client from FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL in .env."""
    load_dotenv()
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=make_credential(),
    )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Turn texts into vectors with FOUNDRY_EMBEDDING_MODEL (one vector per text, same order)."""
    if not texts:
        return []
    load_dotenv()
    async with make_async_credential() as credential:
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

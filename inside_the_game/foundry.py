"""Shared connection to the Microsoft Foundry model, used by every agent."""

import os

from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
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

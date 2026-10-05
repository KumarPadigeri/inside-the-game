import asyncio
import os

from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

load_dotenv()  # reads FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL from .env


async def main():
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=AzureCliCredential(),  # reuses your `az login`
        ),
        name="HelloAgent",
        instructions="You are a football commentator. Keep answers to one sentence.",
    )
    result = await agent.run("Describe a last-minute winning goal.")
    print(f"Agent: {result}")


asyncio.run(main())

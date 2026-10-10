"""Tracing: send OpenTelemetry traces of every recap run to Azure Monitor.

Agent Framework instruments workflows, agents, model calls and tool calls
out of the box; this module only decides where those traces go. They are
sent to the Application Insights resource connected to the Foundry project,
so each run shows up as one timeline: analyst and retrieval in parallel,
then narrator and verifier, with timings and token counts per call.

Prompts and responses are NOT recorded (sensitive data stays off).

Turn it on with TRACING=1 (always on in Azure Container Apps).
"""

from __future__ import annotations

import logging
import os

from opentelemetry.sdk.resources import Resource

from inside_the_game.foundry import make_client, running_in_azure

SERVICE_NAME = "inside-the-game"

_configured = False


def tracing_enabled() -> bool:
    return running_in_azure() or os.environ.get("TRACING", "").lower() in ("1", "true", "yes")


async def setup_tracing() -> bool:
    """Connect traces to Azure Monitor once per process. Returns True if tracing is on.

    Never raises: if Azure Monitor can't be reached, the app keeps working untraced.
    """
    global _configured
    if _configured:
        return True
    if not tracing_enabled():
        return False
    try:
        await make_client().configure_azure_monitor(
            enable_sensitive_data=False,
            resource=Resource.create({"service.name": SERVICE_NAME}),
        )
    except Exception as error:  # noqa: BLE001 - tracing must never break a recap
        logging.warning("Tracing disabled: could not configure Azure Monitor: %s", error)
        return False
    _configured = True
    return True

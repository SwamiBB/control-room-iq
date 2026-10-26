"""Agent Framework client factory.

Uses `agent-framework` (>=1.22) with Azure OpenAI / Foundry. Authentication is Entra ID via
DefaultAzureCredential; no API keys. Each agent calls the model-router deployment for its routing
mode (`deployment_for`, #47); the underlying model chosen per request is recorded in its meta.
If a client or an agent can't be created, the error is logged and the agents affected use their
template fallbacks, so the API still starts.
"""

from __future__ import annotations

import logging
from functools import cache

from .config import deployment_for, settings

logger = logging.getLogger(__name__)


@cache
def chat_client(deployment: str | None = None):
    """One client per deployment: on Azure the deployment is part of the request URL."""
    if settings.offline:
        return None
    try:
        # Chat Completions, not OpenAIChatClient: that one calls the Responses API, which model-router rejects
        # with 400 "The requested operation is unsupported" (#10).
        from agent_framework.openai import OpenAIChatCompletionClient
        from azure.identity import DefaultAzureCredential

        return OpenAIChatCompletionClient(
            azure_endpoint=settings.azure_openai_endpoint or settings.foundry_project_endpoint,
            credential=DefaultAzureCredential(),
            model=deployment or settings.model_router,
        )
    except Exception:  # noqa: BLE001 - the API must still serve the console; these agents fall back to templates
        logger.exception("Model client for %s unavailable; its agents will use their template fallbacks",
                         deployment or settings.model_router)
        return None


def make_agent(name: str, instructions: str, response_format=None):
    """Create an Agent Framework `Agent`. Returns None offline or if it can't be built (callers use fallbacks)."""
    client = chat_client(deployment_for(name))
    if client is None:
        return None
    from agent_framework import Agent

    kwargs = {"name": name, "instructions": instructions}
    # Agent() has no response_format argument; structured output goes through its default chat options.
    options = {"response_format": response_format} if response_format is not None else {}
    if settings.reasoning_effort:
        options["reasoning_effort"] = settings.reasoning_effort
    if options:
        kwargs["default_options"] = options
    try:
        return Agent(client=client, **kwargs)
    except Exception:  # noqa: BLE001 - one agent that can't be built must not stop the API
        logger.exception("Agent %s unavailable; it will use its template fallback", name)
        return None

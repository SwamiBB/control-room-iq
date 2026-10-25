"""Agent Framework client factory.

Uses `agent-framework` (>=1.22) with Azure OpenAI / Foundry. Authentication is Entra ID via
DefaultAzureCredential; no API keys. The model router deployment is used for every agent; the
underlying model chosen per request is recorded in traces. If the client or an agent can't be
created, the error is logged and that agent uses its template fallback, so the API still starts.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from .config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def chat_client():
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
            model=settings.model_router,
        )
    except Exception:  # noqa: BLE001 - the API must still serve the console; every agent falls back to templates
        logger.exception("Model client unavailable; every agent will use its template fallback")
        return None


def make_agent(name: str, instructions: str, response_format=None):
    """Create an Agent Framework `Agent`. Returns None offline or if it can't be built (callers use fallbacks)."""
    client = chat_client()
    if client is None:
        return None
    from agent_framework import Agent

    kwargs = {"name": name, "instructions": instructions}
    if response_format is not None:
        # Agent() has no response_format argument; structured output goes through its default chat options.
        kwargs["default_options"] = {"response_format": response_format}
    try:
        return Agent(client=client, **kwargs)
    except Exception:  # noqa: BLE001 - one agent that can't be built must not stop the API
        logger.exception("Agent %s unavailable; it will use its template fallback", name)
        return None

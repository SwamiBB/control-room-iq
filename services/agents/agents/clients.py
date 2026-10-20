"""Agent Framework client factory.

Uses `agent-framework` (>=1.22) with Azure OpenAI / Foundry. Authentication is Entra ID via
DefaultAzureCredential; no API keys. The model router deployment is used for every agent; the
underlying model chosen per request is recorded in traces.
"""

from __future__ import annotations

from functools import lru_cache

from .config import settings


@lru_cache(maxsize=1)
def chat_client():
    if settings.offline:
        return None
    from agent_framework.openai import OpenAIChatClient
    from azure.identity import DefaultAzureCredential

    return OpenAIChatClient(
        azure_endpoint=settings.azure_openai_endpoint or settings.foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        model=settings.model_router,
    )


def make_agent(name: str, instructions: str, response_format=None):
    """Create an Agent Framework `Agent`. Returns None in offline mode (callers use fallbacks)."""
    client = chat_client()
    if client is None:
        return None
    from agent_framework import Agent

    kwargs = {"name": name, "instructions": instructions}
    if response_format is not None:
        kwargs["response_format"] = response_format
    return Agent(client=client, **kwargs)

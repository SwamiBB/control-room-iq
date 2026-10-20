from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    foundry_project_endpoint: str = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    azure_openai_endpoint: str = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    # Model router deployment handles routing; per-agent routing hints are passed as metadata.
    model_router: str = os.environ.get("MODEL_ROUTER_DEPLOYMENT", "model-router")
    model_fallback: str = os.environ.get("MODEL_FALLBACK_DEPLOYMENT", "gpt-4.1-mini")
    agent_timeout_s: float = float(os.environ.get("AGENT_TIMEOUT_S", "8"))
    offline: bool = os.environ.get("CRQ_OFFLINE", "0") == "1"  # use fallbacks only (tests, demos w/o Azure)
    languages: tuple[str, ...] = tuple(os.environ.get("CRQ_LANGS", "en,es,hi,ar").split(","))


settings = Settings()

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import get_args

from crq_schemas import Lang
from dotenv import load_dotenv

# Must run before Settings is defined: its defaults read os.environ at class-creation time.
load_dotenv()


def _languages() -> tuple[str, ...]:
    """CRQ_LANGS, keeping only languages the schemas support; any other value would fail variant validation."""
    wanted = [x.strip() for x in os.environ.get("CRQ_LANGS", "en,es,hi").split(",") if x.strip()]
    supported = get_args(Lang)
    if dropped := [x for x in wanted if x not in supported]:
        logging.getLogger(__name__).warning("CRQ_LANGS: ignoring unsupported %s (supported: %s)",
                                            ", ".join(dropped), ", ".join(supported))
    return tuple(x for x in wanted if x in supported) or ("en",)


@dataclass(frozen=True)
class Settings:
    foundry_project_endpoint: str = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    azure_openai_endpoint: str = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    # Model router deployment handles routing; per-agent routing hints are passed as metadata.
    model_router: str = os.environ.get("MODEL_ROUTER_DEPLOYMENT", "model-router")
    model_fallback: str = os.environ.get("MODEL_FALLBACK_DEPLOYMENT", "gpt-4.1-mini")
    agent_timeout_s: float = float(os.environ.get("AGENT_TIMEOUT_S", "8"))
    offline: bool = os.environ.get("CRQ_OFFLINE", "0") == "1"  # use fallbacks only (tests, demos w/o Azure)
    languages: tuple[str, ...] = _languages()
    # Routing mode is a per-deployment setting on model router, so one deployment per mode.
    router_quality: str = os.environ.get("ROUTER_QUALITY", "router-quality")
    router_balanced: str = os.environ.get("ROUTER_BALANCED", "router-balanced")
    router_cost: str = os.environ.get("ROUTER_COST", "router-cost")


settings = Settings()

# Routing mode per agent: one model-router deployment per mode (see `router_*` above).
AGENT_ROUTING: dict[str, str] = {"explainer": "quality", "producer": "quality", "narrator": "balanced",
                                 "personalizer": "cost", "localizer": "cost"}


def deployment_for(agent: str) -> str:
    """The router deployment an agent should call; falls back to the single model-router deployment."""
    mode = AGENT_ROUTING.get(agent)
    return {"quality": settings.router_quality, "balanced": settings.router_balanced,
            "cost": settings.router_cost}.get(mode or "", settings.model_router)

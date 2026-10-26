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
    wanted = list(dict.fromkeys(x.strip().lower() for x in os.environ.get("CRQ_LANGS", "en,es,hi").split(",")
                                if x.strip()))
    supported = get_args(Lang)
    if dropped := [x for x in wanted if x not in supported]:
        logging.getLogger(__name__).warning("CRQ_LANGS: ignoring unsupported %s (supported: %s)",
                                            ", ".join(dropped), ", ".join(supported))
    return tuple(x for x in wanted if x in supported) or ("en",)


# What the reasoning models behind the routers accept; gpt-5.1 and later reject "minimal".
REASONING_EFFORTS = ("none", "low", "medium", "high")


def _reasoning_effort() -> str:
    """AGENT_REASONING_EFFORT, checked once here: a value the models reject would fail every call with a 400 and
    quietly turn every card into a template. Empty means send none."""
    value = os.environ.get("AGENT_REASONING_EFFORT", "low").strip().lower()
    if value and value not in REASONING_EFFORTS:
        logging.getLogger(__name__).warning("AGENT_REASONING_EFFORT=%r is not supported (%s); sending none",
                                            value, ", ".join(REASONING_EFFORTS))
        return ""
    return value


@dataclass(frozen=True)
class Settings:
    foundry_project_endpoint: str = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    azure_openai_endpoint: str = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    # Model router deployment handles routing; per-agent routing hints are passed as metadata.
    model_router: str = os.environ.get("MODEL_ROUTER_DEPLOYMENT", "model-router")
    model_fallback: str = os.environ.get("MODEL_FALLBACK_DEPLOYMENT", "gpt-4.1-mini")
    # Per agent call. Moments run in the background (#51), so a slower call delays its card, not the match;
    # 12 s lets an occasional slow router pick finish instead of falling back to the template.
    agent_timeout_s: float = float(os.environ.get("AGENT_TIMEOUT_S", "12"))
    # Passed to the routers, which hand it to the reasoning models they pick. "low" kept every agent under the 8 s
    # timeout in the Oct 26 demo-window runs, with the writing unchanged; the default effort timed out half the
    # explainer calls (#39). Empty sends no reasoning_effort.
    reasoning_effort: str = _reasoning_effort()
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

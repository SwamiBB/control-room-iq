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


# What every reasoning model the routers can pick accepts: gpt-5.1 and later reject "minimal", and gpt-5, gpt-5-mini
# and o4-mini reject "none". To send no effort at all, leave the setting empty.
REASONING_EFFORTS = ("low", "medium", "high")


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
    model_fallback: str = os.environ.get("MODEL_FALLBACK_DEPLOYMENT", "gpt-4.1-mini")
    # Per agent call. Moments run in the background (#51), so a slower call delays its card, not the match;
    # 12 s lets an occasional slow router pick finish instead of falling back to the template.
    agent_timeout_s: float = float(os.environ.get("AGENT_TIMEOUT_S", "12"))
    # Passed to the routers, which hand it to the reasoning models they pick. In the Oct 26 demo-window runs "low"
    # kept every agent call under 8 s with the writing unchanged; the default effort took half the explainer calls
    # past 8 s (#39). Empty sends no reasoning_effort.
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
    """The router deployment an agent should call; an agent with no routing mode gets the balanced router."""
    mode = AGENT_ROUTING.get(agent)
    return {"quality": settings.router_quality, "balanced": settings.router_balanced,
            "cost": settings.router_cost}.get(mode or "", settings.router_balanced)

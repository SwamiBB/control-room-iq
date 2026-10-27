"""Register the five agents in Foundry Agent Service, so they can be inspected (and evaluated) in the portal.

    python -m agents.register_agents            # create or update crq-explainer, crq-narrator, ...
    python -m agents.register_agents --dry-run  # print what would be registered, call nothing

Each agent is a prompt agent bound to its routing mode's model-router deployment (`deployment_for`), with the
same instructions the runtime uses (`agents/prompts/*.md`). The match still runs the agents locally through Agent
Framework; this is the catalogue entry, versioned: an unchanged agent is skipped, a changed one gets a new version.

Needs FOUNDRY_PROJECT_ENDPOINT and the Foundry User role on the project (Entra ID; no keys).
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

from .config import AGENT_ROUTING, deployment_for, registered_name, settings
from .workflow import _prompt

logger = logging.getLogger(__name__)

# What each agent is for, shown in the portal next to its instructions.
PURPOSE = {
    "explainer": "Explains why a match moment matters, citing the events and state it used.",
    "narrator": "Writes the one English on-air line the graphics operator fires.",
    "producer": "Decides whether a moment deserves a graphic, which layer, and for how long.",
    "personalizer": "Rewrites the approved line for newcomer, fan and analyst viewers, and for deaf access.",
    "localizer": "Renders the English versions into Spanish and Hindi, keeping numbers and names exact.",
}


@dataclass(frozen=True)
class AgentSpec:
    name: str  # the agent's name in Foundry
    role: str  # the runtime role: explainer, narrator, ...
    model: str  # the model-router deployment it calls
    routing: str  # quality, balanced or cost
    instructions: str
    description: str


def specs() -> list[AgentSpec]:
    """The five agents as the runtime builds them, in a stable order."""
    return [AgentSpec(name=registered_name(role), role=role, model=deployment_for(role), routing=routing,
                      instructions=_prompt(role), description=PURPOSE[role])
            for role, routing in AGENT_ROUTING.items()]


def _current(client, name: str):
    """The latest version of an agent, or None when it isn't registered yet. Any other error is raised."""
    from azure.core.exceptions import ResourceNotFoundError

    try:
        return next(iter(client.agents.list_versions(name, limit=1, order="desc")), None)
    except ResourceNotFoundError:
        return None


def _metadata(spec: AgentSpec) -> dict[str, str]:
    return {"project": "control-room-iq", "role": spec.role, "routing": spec.routing}


def _unchanged(version, spec: AgentSpec) -> bool:
    """Same model, instructions, description and metadata: nothing worth a new version."""
    definition = getattr(version, "definition", None) or {}
    get = definition.get if hasattr(definition, "get") else lambda k: getattr(definition, k, None)
    return (get("model") == spec.model and get("instructions") == spec.instructions
            and getattr(version, "description", None) == spec.description
            and dict(getattr(version, "metadata", None) or {}) == _metadata(spec))


def register(client, dry_run: bool = False) -> list[tuple[str, str]]:
    """Create or update every agent. Returns (agent name, what happened) pairs."""
    from azure.ai.projects.models import PromptAgentDefinition

    done = []
    for spec in specs():
        if dry_run:
            done.append((spec.name, f"would register on {spec.model} ({spec.routing})"))
            continue
        current = _current(client, spec.name)
        if current is not None and _unchanged(current, spec):
            done.append((spec.name, f"unchanged, version {current.version}"))
            continue
        created = client.agents.create_version(
            spec.name,
            definition=PromptAgentDefinition(model=spec.model, instructions=spec.instructions),
            description=spec.description,
            metadata=_metadata(spec),
        )
        done.append((spec.name, f"registered version {created.version} on {spec.model} ({spec.routing})"))
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print what would be registered; call nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    client = None
    if not args.dry_run:
        if not settings.foundry_project_endpoint:
            parser.error("FOUNDRY_PROJECT_ENDPOINT is not set (azd env get-values > .env)")
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        client = AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=DefaultAzureCredential())
    for name, what in register(client, dry_run=args.dry_run):
        print(f"{name}: {what}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Registering the agents in Foundry Agent Service: what is sent, and that an unchanged agent is skipped."""

import os

os.environ["CRQ_OFFLINE"] = "1"

from types import SimpleNamespace  # noqa: E402

from agents import config  # noqa: E402
from agents.config import registered_name  # noqa: E402
from agents.register_agents import register, specs  # noqa: E402
from agents.workflow import _prompt  # noqa: E402


class FakeAgents:
    def __init__(self, existing=None):
        self.existing = existing or {}
        self.created = []

    def list_versions(self, name, limit=None, order=None):
        from azure.core.exceptions import ResourceNotFoundError

        if name not in self.existing:
            raise ResourceNotFoundError(f"Agent {name} not found")
        return iter([self.existing[name]])

    def create_version(self, name, definition=None, description=None, metadata=None):
        self.created.append((name, dict(definition), description, metadata))
        return SimpleNamespace(version="1")


def test_specs_match_the_runtime_agents():
    by_role = {s.role: s for s in specs()}
    assert set(by_role) == set(config.AGENT_ROUTING)
    for role, s in by_role.items():
        assert s.name == registered_name(role)
        assert s.model == config.deployment_for(role)  # the same router the runtime calls
        assert s.routing == config.AGENT_ROUTING[role]
        assert s.instructions == _prompt(role)  # the same instructions the runtime uses
        assert s.description


def test_new_agents_are_registered_as_prompt_agents():
    client = SimpleNamespace(agents=FakeAgents())
    done = register(client)
    assert len(client.agents.created) == len(config.AGENT_ROUTING)
    name, definition, description, metadata = client.agents.created[0]
    assert definition["kind"] == "prompt" and definition["model"] and definition["instructions"]
    assert metadata["project"] == "control-room-iq" and metadata["routing"] in {"quality", "balanced", "cost"}
    assert all("registered version" in what for _, what in done)


def test_an_unchanged_agent_is_skipped_and_a_changed_one_gets_a_version():
    first = specs()[0]
    same = SimpleNamespace(version="3", definition={"model": first.model, "instructions": first.instructions},
                           description=first.description,
                           metadata={"project": "control-room-iq", "role": first.role, "routing": first.routing})
    second = specs()[1]
    changed = SimpleNamespace(version="2", definition={"model": second.model, "instructions": "old prompt"})
    client = SimpleNamespace(agents=FakeAgents({first.name: same, second.name: changed}))
    done = dict(register(client))
    assert done[first.name] == "unchanged, version 3"
    assert done[second.name].startswith("registered version")
    assert first.name not in [c[0] for c in client.agents.created]


def test_a_new_description_is_a_change():
    first = specs()[0]
    old = SimpleNamespace(version="1", definition={"model": first.model, "instructions": first.instructions},
                          description="old words",
                          metadata={"project": "control-room-iq", "role": first.role, "routing": first.routing})
    client = SimpleNamespace(agents=FakeAgents({first.name: old}))
    assert dict(register(client))[first.name].startswith("registered version")


def test_an_error_other_than_not_found_is_raised():
    import pytest

    class Broken(FakeAgents):
        def list_versions(self, name, limit=None, order=None):
            raise PermissionError("403: no access to the project")

    with pytest.raises(PermissionError):
        register(SimpleNamespace(agents=Broken()))


def test_dry_run_calls_nothing():
    done = register(None, dry_run=True)
    assert len(done) == len(config.AGENT_ROUTING) and all(what.startswith("would register") for _, what in done)

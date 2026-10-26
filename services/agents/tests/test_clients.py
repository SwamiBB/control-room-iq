"""Online agent construction (#9) and language settings (#17). No network calls."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import logging  # noqa: E402

from agent_framework import Agent  # noqa: E402
from agent_framework.openai import OpenAIChatCompletionClient  # noqa: E402
from agents import clients, config  # noqa: E402
from agents.workflow import ExplanationOut, MomentPipeline, ProducerDecision, VariantsOut  # noqa: E402
from crq_schemas import Explanation  # noqa: E402
from openai.lib._pydantic import to_strict_json_schema  # noqa: E402


def _online_client(deployment=None):
    # Placeholder endpoint and token provider: building the client sends no request.
    return OpenAIChatCompletionClient(azure_endpoint="https://example.openai.azure.com/",
                                      credential=lambda: "test-token", model=deployment or "router-balanced")


def test_make_agent_online_sets_structured_output(monkeypatch):
    monkeypatch.setattr(clients, "chat_client", _online_client)
    agent = clients.make_agent("explainer", "Explain the moment.", Explanation)
    assert isinstance(agent, Agent)
    assert agent.default_options["response_format"] is Explanation


def test_pipeline_builds_online(monkeypatch):
    monkeypatch.setattr(clients, "chat_client", _online_client)
    p = MomentPipeline()
    assert all(isinstance(a, Agent) for a in (p.explainer, p.narrator, p.personalizer, p.producer, p.localizer))
    assert p.producer.default_options["response_format"] is ProducerDecision
    assert "response_format" not in p.narrator.default_options
    for n in config.AGENT_ROUTING:  # whatever the developer's .env says, as long as it is passed through
        assert getattr(p, n).default_options.get("reasoning_effort") == (config.settings.reasoning_effort or None)


def test_each_agent_calls_its_routing_modes_deployment(monkeypatch):
    # The routing mode is a deployment setting, so each agent needs a client for its own router (#47).
    monkeypatch.setattr(clients, "chat_client", _online_client)
    p = MomentPipeline()
    assert {n: getattr(p, n).client.model for n in config.AGENT_ROUTING} == {
        n: config.deployment_for(n) for n in config.AGENT_ROUTING}
    assert config.AGENT_ROUTING == {"explainer": "quality", "producer": "quality", "narrator": "balanced",
                                    "personalizer": "cost", "localizer": "cost"}


def test_a_reasoning_effort_the_models_reject_is_not_sent(monkeypatch, caplog):
    for value, sent in (("LOW", "low"), ("high", "high"), ("", ""), ("none", ""), ("minimal", ""), ("lo", "")):
        monkeypatch.setenv("AGENT_REASONING_EFFORT", value)
        with caplog.at_level(logging.WARNING):
            assert config._reasoning_effort() == sent
    assert "'minimal' is not supported" in caplog.text


def test_all_routers_share_one_credential(monkeypatch):
    monkeypatch.setattr(clients, "settings", config.Settings(offline=False,
                                                             azure_openai_endpoint="https://example.openai.azure.com/"))
    clients._client_for.cache_clear()
    clients._credential.cache_clear()
    try:
        a, b = clients.chat_client("router-quality"), clients.chat_client("router-cost")
        assert a is not b and clients._credential() is clients._credential()
        # The default deployment, named or not, is one client.
        balanced = clients.settings.router_balanced
        assert clients.chat_client() is clients.chat_client(None) is clients.chat_client(balanced)
    finally:
        clients._client_for.cache_clear()
        clients._credential.cache_clear()


def test_chat_client_builds_with_real_settings(monkeypatch):
    # The real factory, not a copy of its arguments: a wrong argument would otherwise hide behind the except.
    monkeypatch.setattr(clients, "settings", config.Settings(offline=False,
                                                             azure_openai_endpoint="https://example.openai.azure.com/"))
    clients._client_for.cache_clear()
    try:
        assert isinstance(clients.chat_client(), OpenAIChatCompletionClient)
    finally:
        clients._client_for.cache_clear()


def _open_objects(node, path=""):
    """Paths of objects strict structured output rejects: free-form (additionalProperties not false)."""
    found = []
    if isinstance(node, dict):
        if node.get("type") == "object" and node.get("additionalProperties") is not False:
            found.append(path)
        for k, v in node.items():
            found += _open_objects(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found += _open_objects(v, f"{path}[{i}]")
    return found


def test_structured_outputs_have_no_free_form_objects():
    # model-router answered 400 "additionalProperties ... must be false" for OverlayProposal's payload (#33).
    # This guards that one strict-mode rule; the other keywords these schemas use (enums, minimum/maximum) were
    # accepted by the live router on Oct 25.
    for model in (ExplanationOut, ProducerDecision, VariantsOut):
        assert _open_objects(to_strict_json_schema(model)) == [], model.__name__


def test_client_failure_falls_back_to_templates(monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("constructor changed")

    monkeypatch.setattr(clients, "settings", config.Settings(offline=False,
                                                             azure_openai_endpoint="https://example.openai.azure.com/"))
    monkeypatch.setattr("agent_framework.openai.OpenAIChatCompletionClient", broken)
    clients._client_for.cache_clear()
    try:
        with caplog.at_level(logging.ERROR):
            assert clients.make_agent("explainer", "Explain the moment.", Explanation) is None
        assert "template fallback" in caplog.text
        # The failure is not cached: once the client can be built, that router's next agent gets one.
        monkeypatch.undo()
        monkeypatch.setattr(clients, "settings", config.Settings(
            offline=False, azure_openai_endpoint="https://example.openai.azure.com/"))
        assert isinstance(clients.chat_client(config.deployment_for("explainer")), OpenAIChatCompletionClient)
    finally:
        clients._client_for.cache_clear()


def test_agent_failure_falls_back_to_template(monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise TypeError("unexpected keyword argument")

    monkeypatch.setattr(clients, "chat_client", _online_client)
    monkeypatch.setattr("agent_framework.Agent", broken)
    with caplog.at_level(logging.ERROR):
        assert clients.make_agent("narrator", "Write the line.") is None
    assert "narrator" in caplog.text


def test_languages_drop_unsupported(monkeypatch, caplog):
    monkeypatch.setenv("CRQ_LANGS", "en, es,hi,ar")
    with caplog.at_level(logging.WARNING):
        assert config._languages() == ("en", "es", "hi")
    assert "ar" in caplog.text


def test_languages_ignore_case_and_duplicates(monkeypatch):
    monkeypatch.setenv("CRQ_LANGS", "EN, es, Es,hi")
    assert config._languages() == ("en", "es", "hi")


def test_languages_fall_back_to_english(monkeypatch):
    monkeypatch.setenv("CRQ_LANGS", "ar,fr")
    assert config._languages() == ("en",)

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


def _online_client():
    # Placeholder endpoint and token provider: building the client sends no request.
    return OpenAIChatCompletionClient(azure_endpoint="https://example.openai.azure.com/",
                                      credential=lambda: "test-token", model="model-router")


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


def test_chat_client_builds_with_real_settings(monkeypatch):
    # The real factory, not a copy of its arguments: a wrong argument would otherwise hide behind the except.
    monkeypatch.setattr(clients, "settings", config.Settings(offline=False,
                                                             azure_openai_endpoint="https://example.openai.azure.com/"))
    clients.chat_client.cache_clear()
    try:
        assert isinstance(clients.chat_client(), OpenAIChatCompletionClient)
    finally:
        clients.chat_client.cache_clear()


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


def test_structured_outputs_are_strict_schema_safe():
    # model-router answered 400 "additionalProperties ... must be false" for OverlayProposal's payload (#33).
    for model in (ExplanationOut, ProducerDecision, VariantsOut):
        assert _open_objects(to_strict_json_schema(model)) == [], model.__name__


def test_client_failure_falls_back_to_templates(monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("constructor changed")

    monkeypatch.setattr(clients, "settings", config.Settings(offline=False,
                                                             azure_openai_endpoint="https://example.openai.azure.com/"))
    monkeypatch.setattr("agent_framework.openai.OpenAIChatCompletionClient", broken)
    clients.chat_client.cache_clear()
    try:
        with caplog.at_level(logging.ERROR):
            assert clients.make_agent("explainer", "Explain the moment.", Explanation) is None
        assert "template fallback" in caplog.text
    finally:
        clients.chat_client.cache_clear()


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

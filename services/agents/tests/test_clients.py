"""Online agent construction (#9) and language settings (#17). No network calls."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import logging  # noqa: E402

from agent_framework import Agent  # noqa: E402
from agent_framework.openai import OpenAIChatClient  # noqa: E402
from agents import clients, config  # noqa: E402
from agents.workflow import MomentPipeline  # noqa: E402
from crq_schemas import Explanation, OverlayProposal  # noqa: E402


def _online_client():
    # Placeholder endpoint and token provider: building the client sends no request.
    return OpenAIChatClient(azure_endpoint="https://example.openai.azure.com/", credential=lambda: "test-token",
                            model="model-router")


def test_make_agent_online_sets_structured_output(monkeypatch):
    monkeypatch.setattr(clients, "chat_client", _online_client)
    agent = clients.make_agent("explainer", "Explain the moment.", Explanation)
    assert isinstance(agent, Agent)
    assert agent.default_options["response_format"] is Explanation


def test_pipeline_builds_online(monkeypatch):
    monkeypatch.setattr(clients, "chat_client", _online_client)
    p = MomentPipeline()
    assert all(isinstance(a, Agent) for a in (p.explainer, p.narrator, p.personalizer, p.producer, p.localizer))
    assert p.producer.default_options["response_format"] is OverlayProposal
    assert "response_format" not in p.narrator.default_options


def test_client_failure_falls_back_to_templates(monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("constructor changed")

    monkeypatch.setattr(clients, "settings", config.Settings(offline=False,
                                                             azure_openai_endpoint="https://example.openai.azure.com/"))
    monkeypatch.setattr("agent_framework.openai.OpenAIChatClient", broken)
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


def test_languages_fall_back_to_english(monkeypatch):
    monkeypatch.setenv("CRQ_LANGS", "ar,fr")
    assert config._languages() == ("en",)

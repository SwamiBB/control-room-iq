"""Traces: one per moment with its card, and the decision and airing linked back to it."""

import asyncio

import api.main as main
import pytest
from agents.workflow import MomentResult, fallback_explanation
from api.main import ViewerPrefs, _run_moment, app, hub
from api_factories import RecordingSocket, moment, proposal
from crq_schemas import Persona
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from simulator.cli import build_meta

SPANS = None  # the shared in-memory exporter (services/conftest.py), set for each test


@pytest.fixture(autouse=True)
def _spans(spans):
    global SPANS
    SPANS = spans


def _named(name):
    return [s for s in SPANS.get_finished_spans() if s.name == name]


def _moment_with_card(monkeypatch):
    m = moment()
    card = proposal("p-card")

    async def process(_m, on_card=None, **_kwargs):
        res = MomentResult(moment=m, explanation=fallback_explanation(m), line="l", variants=[], proposal=card,
                           failures=[])
        await on_card(res)
        return res

    monkeypatch.setattr(main.pipeline, "process", process)
    asyncio.run(_run_moment(m))
    return m


def test_a_moment_is_one_trace_that_records_its_card(monkeypatch):
    m = _moment_with_card(monkeypatch)
    (span,) = _named("crq.moment")
    assert span.attributes["crq.moment_id"] == m.moment_id and span.attributes["crq.kind"] == "big_chance"
    assert span.attributes["crq.card"] is True and span.attributes["crq.failures"] == 0
    (event,) = [e for e in span.events if e.name == "card on the desk"]
    assert event.attributes["crq.proposal_id"] == "p-card"
    assert hub.moment_traces[m.moment_id] == span.get_span_context()


def test_the_decision_and_the_airing_link_back_to_the_moment(monkeypatch):
    _moment_with_card(monkeypatch)
    (moment_span,) = _named("crq.moment")
    hub.viewers[RecordingSocket()] = ViewerPrefs(persona=Persona.FAN, access="none", lang="es")

    TestClient(app).post("/proposals/p-card/approve")

    (decision,) = _named("crq.decision")
    assert decision.attributes["crq.action"] == "approved" and decision.attributes["crq.proposal_id"] == "p-card"
    assert [link.context for link in decision.links] == [moment_span.get_span_context()]
    (air,) = _named("crq.air")
    assert [link.context for link in air.links] == [moment_span.get_span_context()]
    assert sum(air.attributes[f"crq.groups.{s}"] for s in ("variant", "template", "base", "override")) == 1
    (delivered,) = [e for e in air.events if e.name == "delivered"]
    assert delivered.attributes["crq.group"] == "fan.none.es"


def test_a_failed_moment_is_recorded_on_its_trace(monkeypatch):
    async def process(_m, **_kwargs):
        raise RuntimeError("the agents broke")

    monkeypatch.setattr(main.pipeline, "process", process)
    asyncio.run(_run_moment(moment()))
    (span,) = _named("crq.moment")
    assert any(e.name == "exception" for e in span.events)
    assert span.status.status_code == StatusCode.ERROR  # counted as a failure in App Insights


def test_each_moment_is_its_own_trace_even_inside_the_request_that_started_the_replay(monkeypatch):
    _moment_with_card(monkeypatch)
    with trace.get_tracer("test").start_as_current_span("POST /matches/replay") as request:
        asyncio.run(_run_moment(moment("mo-2")))
    first, second = _named("crq.moment")
    assert second.parent is None and second.context.trace_id != request.get_span_context().trace_id
    assert first.context.trace_id != second.context.trace_id


def test_a_moment_cancelled_by_a_new_match_is_not_an_error(monkeypatch):
    async def process(_m, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(main.pipeline, "process", process)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_run_moment(moment()))
    (span,) = _named("crq.moment")
    assert span.attributes["crq.cancelled"] is True and span.status.status_code != StatusCode.ERROR


def test_an_operator_s_decision_sits_in_their_request_and_links_to_the_moment(monkeypatch):
    _moment_with_card(monkeypatch)
    (moment_span,) = _named("crq.moment")
    with trace.get_tracer("test").start_as_current_span("POST /proposals/p-card/hold") as request:
        TestClient(app).post("/proposals/p-card/hold")
    (decision,) = _named("crq.decision")
    assert decision.parent.span_id == request.get_span_context().span_id and decision.attributes["crq.action"] == "held"
    assert [link.context for link in decision.links] == [moment_span.get_span_context()]


def test_background_work_starts_its_own_trace_not_the_request_s(monkeypatch):
    seen = {}

    async def background_work():
        seen["parent"] = trace.get_current_span().get_span_context().is_valid

    async def from_a_request():
        with trace.get_tracer("test").start_as_current_span("POST /matches/replay"):
            await main._background(background_work())

    asyncio.run(from_a_request())
    assert seen == {"parent": False}  # the replay, a moment or the timer: no request span to keep adding to


def test_a_moment_that_waited_for_a_slot_says_how_long(monkeypatch):
    _moment_with_card(monkeypatch)
    (span,) = _named("crq.moment")
    assert span.attributes["crq.slot_wait_ms"] >= 0


def test_a_failure_after_the_card_is_on_the_desk_is_recorded_on_the_moment(monkeypatch):
    m = moment()
    card = proposal("p-late-fail")

    async def process(_m, on_card=None, **_kwargs):
        await on_card(MomentResult(moment=m, explanation=fallback_explanation(m), line="l", variants=[],
                                   proposal=card, failures=[]))
        raise RuntimeError("the localizer broke")

    monkeypatch.setattr(main.pipeline, "process", process)
    asyncio.run(_run_moment(m))
    (span,) = _named("crq.moment")
    assert span.status.status_code == StatusCode.ERROR and span.attributes["crq.card"] is True
    assert "versions: failed after the card; templates used" in span.attributes["crq.failure_reasons"]


def test_a_new_match_forgets_the_last_run_s_traces(monkeypatch):
    m = _moment_with_card(monkeypatch)
    hub.new_match(build_meta(42))
    assert m.moment_id not in hub.moment_traces


def test_tracing_is_off_without_a_connection_string(monkeypatch):
    from agents import telemetry

    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    assert telemetry.configure("crq-test") is False
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000-0000-0000-0")
    assert telemetry.settings.offline  # the tests run offline, as demos without Azure do: those never export
    assert telemetry.configure("crq-test") is False

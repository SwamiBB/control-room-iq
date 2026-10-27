"""OpenTelemetry traces to Application Insights, which the Foundry project is connected to (Observability > Traces).

One trace per moment: `crq.moment` (API) holds a `crq.agent <role>` span per agent, and inside each, Agent
Framework's own `invoke_agent` and `chat` spans (tokens, the model the router chose). A decision on the moment's
card, and its airing, are spans of their own that link back to that trace.

Off unless APPLICATIONINSIGHTS_CONNECTION_STRING is set, which Bicep does for the hosted apps only: laptops and CI
send nothing. Ingestion is Entra ID only (the resource has local auth off), with the same credential as the models.
CRQ_TRACE_CONTENT=true adds prompt and response text to the spans; the hosted demo turns it on because all match
data is synthetic. A deployment with real viewer data would leave it off.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace

from .config import settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("control-room-iq")

# Only requests that change something are traced (a fire, hold, override or drop; a replay starting). The read-only
# polls (each viewer every 2 s, each console every 5 s), the health probe and the long-lived sockets would bury them
# under thousands of empty spans.
_NOT_TRACED = ",".join([
    "healthz", "ws/", "/state", "/proposals$", "/proposals/[^/]+/preview", "/decisions", "/deliveries", "/metrics",
    "/schedule", "/recap", "/viewer-groups", "/packages/[^/]+$",
])
_on = False


def configure(service_name: str) -> bool:
    """Start exporting traces, once, at process start. Returns whether tracing is on."""
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
    if not connection_string or settings.offline:
        return False
    try:
        from agent_framework.observability import enable_instrumentation
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.sdk.resources import Resource

        from .clients import _credential

        # Every trace is kept. The default limits it to 5 traces a second, and a moment's agent, model and Event Hubs
        # spans alone pass that, so whole traces were dropped: an operator's fire went missing with its decision
        # and airing. The demo's volume is small; a busy production deployment would sample.
        configure_azure_monitor(connection_string=connection_string, credential=_credential(), sampling_ratio=1.0,
                                resource=Resource.create({"service.name": service_name}))
    except Exception:  # noqa: BLE001 - tracing must never stop the API
        logger.exception("Tracing to Application Insights unavailable; continuing without it")
        return False
    global _on
    _on = True  # exporting from here on, whatever happens to the agents' instrumentation below
    try:
        enable_instrumentation(enable_sensitive_data=settings.trace_content)
    except Exception:  # noqa: BLE001
        logger.exception("Agent Framework spans unavailable; the app's own spans are still traced")
    return True


def brief(reason: str) -> str:
    """A failure reason fit for telemetry: with trace content off, the error's type and not its message, which can
    quote the model's reply (a validation error does). Content on (synthetic data) keeps it whole."""
    return reason if settings.trace_content else ": ".join(reason.split(": ")[:2])


def instrument_app(app) -> None:
    """Trace the API's requests (an operator's fire, hold or override; a replay starting). Done on the app itself:
    Azure Monitor patches the FastAPI class, which misses an app module that imported FastAPI before tracing began."""
    if not _on:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls=_NOT_TRACED, exclude_spans=["receive", "send"])
    except Exception:  # noqa: BLE001 - tracing must never stop the API
        logger.exception("Request tracing unavailable; continuing without it")

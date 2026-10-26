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

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("control-room-iq")

# Long-lived sockets and the health probe would each be one span lasting minutes, or thousands of empty ones.
_NOT_TRACED = "healthz,ws/.*"


def configure(service_name: str) -> bool:
    """Start exporting traces, once, at process start. Returns whether tracing is on."""
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
    if not connection_string or os.environ.get("CRQ_OFFLINE", "0") == "1":
        return False
    try:
        from agent_framework.observability import enable_instrumentation
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.sdk.resources import Resource

        from .clients import _credential

        os.environ.setdefault("OTEL_PYTHON_FASTAPI_EXCLUDED_URLS", _NOT_TRACED)
        configure_azure_monitor(connection_string=connection_string, credential=_credential(),
                                resource=Resource.create({"service.name": service_name}))
        enable_instrumentation(enable_sensitive_data=os.environ.get("CRQ_TRACE_CONTENT", "").lower() == "true")
        return True
    except Exception:  # noqa: BLE001 - tracing must never stop the API
        logger.exception("Tracing to Application Insights unavailable; continuing without it")
        return False

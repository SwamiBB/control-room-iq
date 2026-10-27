"""Shared by the agents' and the API's tests."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# One provider and one in-memory exporter for the whole run: a provider can be set once per process.
_SPANS = InMemorySpanExporter()
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(_SPANS))


@pytest.fixture
def spans() -> InMemorySpanExporter:
    """The spans finished during the test (telemetry.py's tracer; no export)."""
    _SPANS.clear()
    return _SPANS

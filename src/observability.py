"""Tracing setup shared by every app and worker.

Call `configure_tracing()` once at process start; import `tracer` anywhere.
`OTEL_SERVICE_NAME` and the `OTEL_EXPORTER_OTLP_*` settings are read by the SDK itself.
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from config import settings

# Resolves lazily, so importing this before configure_tracing() runs is safe.
tracer = trace.get_tracer("rag")


def configure_tracing() -> None:
    """Idempotent. Records spans locally; exports only if an OTLP endpoint is set."""
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return

    provider = TracerProvider(
        resource=Resource.create({"deployment.environment": settings.environment})
    )
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

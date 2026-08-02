"""Tracing setup shared by every app and worker.

Call `configure_tracing()` once at process start; import `tracer` anywhere.
The exporter endpoint is read from OTEL_EXPORTER_OTLP_ENDPOINT by the SDK.
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from config import settings

# A lazy proxy, so importing this before configure_tracing() runs is safe.
tracer = trace.get_tracer("rag")


def configure_tracing() -> None:
    """Idempotent. Records spans locally; exports only when an endpoint and key are set."""
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return

    provider = TracerProvider(
        resource=Resource.create({"deployment.environment": settings.environment})
    )
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") and settings.honeycomb_api_key:
        # Built here rather than passed via OTEL_EXPORTER_OTLP_HEADERS, whose value the
        # SDK writes to the log when it cannot parse it.
        exporter = OTLPSpanExporter(
            headers={"x-honeycomb-team": settings.honeycomb_api_key.get_secret_value()}
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

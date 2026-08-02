"""Tracing setup shared by every app and worker.

Call `configure_tracing()` once at process start; import `tracer` anywhere.
The endpoint comes from `OTEL_EXPORTER_OTLP_ENDPOINT`, which the SDK reads itself.

Auth headers are built here from the API key rather than passed through
`OTEL_EXPORTER_OTLP_HEADERS`. That variable is a plain string the SDK parses at startup,
and on a malformed value it logs the string it failed to parse, which puts the key in
stdout and from there into CloudWatch. Passing the key as its own variable removes both
the parsing step and the log line.
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
    """Idempotent. Records spans locally; exports only if an endpoint and key are set."""
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return

    provider = TracerProvider(
        resource=Resource.create({"deployment.environment": settings.environment})
    )
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") and settings.honeycomb_api_key:
        exporter = OTLPSpanExporter(
            headers={"x-honeycomb-team": settings.honeycomb_api_key.get_secret_value()}
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

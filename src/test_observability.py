from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from observability import configure_tracing, tracer


def test_configure_tracing_is_idempotent_and_records_spans() -> None:
    configure_tracing()
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)

    configure_tracing()
    assert trace.get_tracer_provider() is provider

    with tracer.start_as_current_span("check") as span:
        assert span.get_span_context().trace_id != 0

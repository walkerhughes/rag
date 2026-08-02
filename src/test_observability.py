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


def test_the_service_name_and_version_reach_the_resource() -> None:
    """Traces are useless for a deploy question without the commit that produced them."""
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    attributes = provider.resource.attributes
    assert "service.version" in attributes
    # The current spelling. `deployment.environment` without the suffix is deprecated.
    assert "deployment.environment.name" in attributes

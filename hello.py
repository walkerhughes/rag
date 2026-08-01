from opentelemetry import trace

tracer = trace.get_tracer(__name__)


def main():
    with tracer.start_as_current_span("greet") as span:
        span.set_attribute("greeting.target", "rag")
        print("Hello from rag!")


if __name__ == "__main__":
    main()

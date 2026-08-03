"""HTTP API for the rag service."""

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from config import settings
from observability import configure_tracing

configure_tracing("rag-api")

app = FastAPI(title="rag")
FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    """Load balancer health check. Reports the revision that tags every span."""
    return {"status": "ok", "revision": settings.service_version}

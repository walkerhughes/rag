"""HTTP API for the rag service."""

import os

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from observability import configure_tracing

configure_tracing()

app = FastAPI(title="rag")
FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    """Load balancer health check. Reports the revision the image was built from."""
    return {"status": "ok", "revision": os.getenv("GIT_SHA", "unknown")}

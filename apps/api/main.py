"""The deployable API.

Today it serves only a health check. Its job at this stage is to prove the path from
source to a running AWS service, so that #10 has somewhere to land the agent rather than
debugging deployment and the agent loop at the same time.
"""

import os

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from observability import configure_tracing

configure_tracing()

app = FastAPI(title="rag")
FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    """Load balancer target. Reports the running image so a rollback is verifiable."""
    return {"status": "ok", "revision": os.getenv("GIT_SHA", "unknown")}

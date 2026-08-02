# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Dependencies resolve from the lockfile in their own layer, so application edits do not
# reinstall them. --frozen fails the build if the lockfile drifts from pyproject.toml.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY apps/ ./apps/

ENV PYTHONPATH=/app/src \
    PATH=/app/.venv/bin:$PATH

ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# rag

Agentic GraphRAG over speaker-attributed Dwarkesh Podcast transcripts.
Postgres is the canonical store; Neo4j, when it arrives, is a rebuildable projection.
See [#1](https://github.com/walkerhughes/rag/issues/1) for the roadmap.

## Setup

```bash
uv sync
```

Set the OTEL variables in `.env` to export traces to Honeycomb. Without them the app
still records spans locally, so nothing needs a network to run.

## Checks

CI runs exactly these, in this order:

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src apps && uv run pytest --cov
```

`.claude/hooks/format.sh` runs `ruff format` on every Python file Claude edits, so the
working tree stays formatted between check runs. It sorts imports but deliberately does
not strip unused ones, which would delete an import written just before its first use.

## Layout

`src/` is the import root. Capability modules start flat and become packages when they
grow a second file. Tests sit beside the code they cover.

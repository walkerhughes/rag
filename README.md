# rag

Agentic GraphRAG over speaker-attributed Dwarkesh Podcast transcripts.
Postgres is the canonical store; Neo4j, when it arrives, is a rebuildable projection.
See [#1](https://github.com/walkerhughes/rag/issues/1) for the roadmap.

## Setup

```bash
uv sync
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT` and `HONEYCOMB_API_KEY` in `.env` to export traces.
Without them the app still records spans locally, so nothing needs a network to run.

The key is passed as its own variable rather than through `OTEL_EXPORTER_OTLP_HEADERS`,
because the SDK logs that variable's value when it fails to parse it.

Run the API locally:

```bash
uv run uvicorn apps.api.main:app --reload
```

## Deploying

The stack is ECR, a two-AZ VPC, and one Fargate service behind an ALB, serving
`/health`. Roughly $36/month, of which the load balancer and its public IPv4 addresses
are two thirds. Postgres, Neo4j, and the ingestion worker arrive with the issues that
need them, so nothing sits idle on the bill.

State lives in `s3://rag-pulumi-state-682033482233`, with stack secrets encrypted by the
`alias/rag-pulumi` KMS key. No Pulumi Cloud account is involved.

```bash
export AWS_PROFILE=walker-rag-app
pulumi login s3://rag-pulumi-state-682033482233
cd infra && pulumi up
```

`pulumi config set --secret honeycombApiKey <key>` seeds the key into SSM. Check what a
change would do before making it:

```bash
cd infra && pulumi preview
```

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

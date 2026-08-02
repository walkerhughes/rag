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

## Local database

`make up` starts Postgres with pgvector, waits for its healthcheck, and migrates to head.
`make down` stops it and keeps the data; `make reset` discards the volume and rebuilds
from migrations alone, which is the fastest way to prove migrations still work from empty.

```bash
make up      # start and migrate
make psql    # a shell on the database
make reset   # throw it away and rebuild
make down    # stop
```

It listens on **5433**, not 5432, so it never collides with a Postgres already installed
on the host. `DATABASE_URL` overrides the default.

## Migrations

Alembic owns the schema. Application code never creates tables, and `Base.metadata` is
the single description of what the schema should be.

```bash
uv run alembic revision --autogenerate -m "add episodes"
uv run alembic upgrade head
uv run alembic downgrade -1
```

`make test-integration` checks that a clean database reaches head, that the schema at head
matches the models, and that a downgrade to base leaves nothing behind. CI runs the same
tests against a Postgres service container, so a model change without a migration fails
the build.

**Roll forward by default.** A migration that has run anywhere other than a developer's
machine is history: fix it with a new migration rather than editing it. `downgrade` is
written for every migration and tested, but it is a local development tool and a last
resort in an emergency, not the normal way to undo a change.

**Expand, then contract.** Deployed code and the schema change at different moments, so a
single migration must never break the currently running version. Add a column, deploy code
that writes it, backfill, then drop the old one in a later migration.

## Deploying

The stack is ECR, a two-AZ VPC, and one Fargate service behind an ALB, serving
`/health`. Roughly $36/month, of which the load balancer and its public IPv4 addresses
are two thirds. Postgres, Neo4j, and the ingestion worker arrive with the issues that
need them, so nothing sits idle on the bill.

State lives in `s3://rag-pulumi-state-682033482233`, encrypted by the `alias/rag-pulumi`
KMS key. No Pulumi Cloud account is involved, so no Pulumi access token is needed.

`GIT_SHA` is baked into the image and reported by `/health`, so the running revision is
identifiable. It defaults to `unknown` when unset.

```bash
export AWS_PROFILE=walker-rag-app
export GIT_SHA=$(git rev-parse --short HEAD)
pulumi login s3://rag-pulumi-state-682033482233
cd infra && pulumi preview   # then: pulumi up
```

### Secrets

No secret material is committed, and none passes through the Pulumi program or its state
file. Pulumi creates each SSM parameter empty and ignores later changes to its value; the
value is written separately, from a GitHub Actions secret or by hand:

```bash
aws ssm put-parameter --name /rag/dev/honeycomb-api-key \
  --type SecureString --overwrite --value "$HONEYCOMB_API_KEY"
```

Secrets are injected when a task starts, so a running service picks up a new value only
after its next deployment:

```bash
aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment
```

## Checks

`make check` runs exactly what CI runs, in the same order. Integration tests are excluded
from it because they need a database; `make test-integration` runs those.

`.claude/hooks/format.sh` runs `ruff format` on every Python file Claude edits, so the
working tree stays formatted between check runs. It sorts imports but deliberately does
not strip unused ones, which would delete an import written just before its first use.

## Layout

`src/` is the import root. Capability modules start flat and become packages when they
grow a second file. Tests sit beside the code they cover.

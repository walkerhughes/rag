# rag

An agentic GraphRAG system over speaker-attributed Dwarkesh Podcast transcripts.

Ask questions that span episodes ("where do Sutton and Karpathy disagree about continual
learning?") and get answers grounded in transcript passages, with citations. Postgres is
the canonical store. Neo4j, when it arrives, is a projection that can be rebuilt from it.

See [#1](https://github.com/walkerhughes/rag/issues/1) for the roadmap and
[CLAUDE.md](CLAUDE.md) for the standards this repo is developed under.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Docker, for the local database
- AWS CLI and Pulumi, only if you are deploying

## Quickstart

```bash
uv sync
make up
PYTHONPATH=src uv run uvicorn apps.api.main:app --reload
curl localhost:8000/health
```

`make up` starts Postgres and migrates it to head. The API answers on port 8000.

## Commands

| | |
| --- | --- |
| `make up` | Start Postgres and migrate to head |
| `make down` | Stop it, keeping the data |
| `make reset` | Discard the data and rebuild from migrations |
| `make psql` | Open a shell on the database |
| `make preview` | Parse an episode without writing, to check it first. No database needed |
| `make ingest` | Ingest recent episodes (`LIMIT=10`, or `SLUG=richard-sutton`) |
| `make reindex` | Rebuild chunks and the search index, fetching nothing |
| `make eval-retrieval` | Score the examples against each retrieval strategy (`SPLIT=heldout`) |
| `make check` | Everything CI runs: format, lint, types, unit tests |
| `make test-integration` | Tests that need the database |

New migration:

```bash
uv run alembic revision --autogenerate -m "add episodes"
```

## Configuration

Settings come from the environment, or from `.env` locally. Everything has a working
default except the Honeycomb key.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Defaults to the docker-compose database |
| `OPENSEARCH_URL` | Defaults to the docker-compose search node |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Where traces go. Unset means spans stay in-process |
| `HONEYCOMB_API_KEY` | Sent as `x-honeycomb-team`. The key picks the Honeycomb environment |
| `ENVIRONMENT` | Tags spans as `deployment.environment.name`. `local` by default |
| `GIT_SHA` | Tags spans as `service.version`. Baked in at image build |

The local database listens on **5433**, not 5432, so it does not collide with a Postgres
already installed on your machine.

## Layout

```
apps/api/        HTTP entrypoint
src/             capability modules, tests beside the code
  config.py        settings
  observability.py tracing
  retrieval/       chunking and search
  storage/         database and migrations
docs/evaluation/ the question classes the system claims to answer
infra/           Pulumi program for AWS
```

## Deploying

The stack is ECR, a two-AZ VPC, and one Fargate service behind a load balancer. Roughly
$36/month, mostly the load balancer. Deployment is manual and nothing runs today.

```bash
export AWS_PROFILE=walker-rag-app
export GIT_SHA=$(git rev-parse --short HEAD)
pulumi login s3://rag-pulumi-state-682033482233
cd infra && pulumi preview
```

Secrets are not stored in the repository. Pulumi creates the SSM parameters empty and the
values are written separately:

```bash
aws ssm put-parameter --name /rag/dev/honeycomb-api-key \
  --type SecureString --overwrite --value "$HONEYCOMB_API_KEY"
```

Because secrets are read when a task starts, a running service picks up a new value only
after `aws ecs update-service --force-new-deployment`.

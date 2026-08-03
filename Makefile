.PHONY: up down reset logs psql preview ingest reindex eval-retrieval check test test-integration

# Starts Postgres, waits for it to pass its healthcheck, and migrates it to head.
up:
	docker compose up -d --wait
	uv run alembic upgrade head

# Stops the containers. The data volume survives, so `make up` returns to the same state.
down:
	docker compose down

# Discards the data volume and rebuilds the database from migrations alone.
reset:
	docker compose down -v
	$(MAKE) up

LIMIT ?= 5

logs:
	docker compose logs -f postgres

psql:
	docker compose exec postgres psql -U rag -d rag

# Fetches and parses without writing, to check a parse before ingesting for real.
# Needs no database. Pass SLUG=<slug> for one episode.
preview:
	PYTHONPATH=src uv run python -m apps.ingestion_worker.main --dry-run $(if $(SLUG),--slug $(SLUG),--limit $(LIMIT))

# Ingests recent episodes from dwarkesh.com. Pass SLUG=<slug> for one episode.
ingest: up
	PYTHONPATH=src uv run python -m apps.ingestion_worker.main $(if $(SLUG),--slug $(SLUG),--limit $(LIMIT))

# Rebuilds chunks for every stored episode. Fetches nothing.
reindex: up
	PYTHONPATH=src uv run python -m apps.ingestion_worker.main --reindex

# Scores the evaluation examples against every retrieval strategy and prints the report.
# Measures whatever is ingested locally, which the report names. Pass SPLIT=heldout for
# the release-gate examples, or K=3 for a single rank.
eval-retrieval: up
	PYTHONPATH=src uv run python -m apps.retrieval_eval.main $(if $(SPLIT),--split $(SPLIT),) $(if $(K),--k $(K),)

# The same commands CI runs, in the same order.
check:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy src apps
	uv run pytest -m "not integration" --cov

test:
	uv run pytest -m "not integration"

# Needs the database, so it brings it up first.
test-integration: up
	uv run pytest -m integration

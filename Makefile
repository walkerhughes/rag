.PHONY: up down reset logs psql check test test-integration

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

logs:
	docker compose logs -f postgres

psql:
	docker compose exec postgres psql -U rag -d rag

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

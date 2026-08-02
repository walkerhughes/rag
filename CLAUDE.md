# Repository standards

The working agreement for this repo. The README is the human introduction to the project;
this file is the set of standards to follow when changing it.

## Comments

Say what the code is, in a sentence or two. Do not cite issue numbers, describe planned
future states, or narrate the reasoning behind a decision at length. That context belongs
in the pull request or the issue, where it stays accurate.

A real hazard is worth one factual sentence.

## Layout

`src/` is the import root, through pytest `pythonpath` rather than an installed
distribution, so generic names like `config` cannot collide with a dependency.

Capability modules start as a single file and become packages when they grow a second one.
Tests sit beside the code they cover. Do not create package directories before there is
code to put in them.

## Checks

`make check` runs what CI runs, in the same order: ruff format, ruff check, mypy over
`src` and `apps`, then pytest excluding integration tests. Run it before pushing.

Tests needing Postgres carry `@pytest.mark.integration` and run through
`make test-integration`. The unit suite never needs a network or a database.

## Dependencies

Add an OpenTelemetry instrumentation package alongside the library it instruments, never
ahead of it. `opentelemetry-distro` is deliberately absent: it exists to support zero-code
`opentelemetry-instrument` startup, and `src/observability.py` configures the SDK directly.

## Migrations

Alembic owns the schema. Application code never creates tables. `Base.metadata` is the
single description of what the schema should be, and CI fails when the two drift apart.

**Roll forward by default.** A migration that has run anywhere other than a developer's
machine is history: fix it with a new migration rather than editing it. Write and test
`downgrade` for every migration, but treat it as a local tool and an emergency measure,
not the normal way to undo a change.

**Expand, then contract.** Deployed code and the schema change at different moments, so a
single migration must never break the version currently running. Add a column, deploy code
that writes it, backfill, then drop the old one in a later migration.

## Secrets

No secret material belongs in the repository, the Pulumi program, or its state file.
Pulumi creates SSM parameters empty and ignores later changes to their values; the values
are written separately from a GitHub Actions secret.

Credentials in settings are `SecretStr`, so logging a `Settings` object or letting one
reach a traceback prints a mask rather than the value. Never pass a key through
`OTEL_EXPORTER_OTLP_HEADERS`: the OpenTelemetry SDK writes that variable's value to the
log when it cannot parse it.

## Infrastructure

Pulumi, not Terraform. `infra/` is a Python program whose state lives in S3 and whose
secrets are encrypted with KMS, so no Pulumi Cloud account and no access token are
involved.

Run `pulumi preview` before `pulumi up`, and read the plan. Deployment is manual.

## Evaluation contract

`docs/evaluation/` is machine-readable and guarded by `src/test_evaluation_contract.py`.
Adding a question class means adding both development and held-out examples, or CI fails.

Quality floors written before a capability was measured are provisional, and must be
labelled as such. A floor that looks measured but is not is worse than no floor.

## Pull requests

Open pull requests as drafts. Do not merge without an explicit go-ahead.

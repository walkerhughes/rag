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

## Ingestion

Check a parse with `make preview SLUG=<slug>` before ingesting for real. It fetches and
parses without writing and needs no database, and its report shows the turn count,
speakers, word count, timestamp coverage, longest turn, and the first and last turns.

The archive's `type` field is not a reliable indicator that a post has a transcript: some
essays are published as podcasts. A page that yields no speaker turns is quarantined
rather than stored empty.

## Layering

Document ingestion and retrieval must stay independent, so either can be replaced without
touching the other. Reusing retrieval on a different corpus should mean writing a new
ingestion layer and a schema, and nothing else.

```
apps/                      entry points, where the layers are composed
  corpus/     ingestion  ─┐
  retrieval/  search     ─┴─> storage/ ─> config/, observability/
```

`corpus` and `retrieval` never import each other. `storage` holds the schema and imports
neither, so it knows nothing about what fills it or reads it. Persistence belongs to the
layer that owns the concept: episodes to `corpus`, chunks to `retrieval`. Chunking
declares the turn shape it needs rather than importing the corpus model.

`src/test_layering.py` walks the import graph and fails on a violation. Add a layer to
`ALLOWED` there before introducing it.

## Retrieval

Chunks pack consecutive turns toward two hundred words and split a longer turn at
sentence boundaries, because a turn is the wrong unit on its own: a quarter of real turns
are under twenty words and a tenth run past three hundred. Chunks never cross episodes,
and each records the range of turns it covers so a passage resolves back to its speaker
and position.

Every strategy returns `Evidence`, so results from different strategies can be compared
and cited the same way, and they share chunk identifiers so a citation resolves the same
whichever strategy found it.

Two lexical strategies exist on purpose. Postgres full-text ranking has no term-rarity
weighting; OpenSearch gives BM25, which does. Keeping both lets the evaluation harness
measure the difference rather than assume it. The search index is a projection of the
chunk table and can be dropped and rebuilt at any time.

Full-text queries match any of a question's terms, not all of them. Requiring every term
makes a natural-language question unmatchable, which reads as a retrieval failure when it
is really a query-construction bug. Ranked results break ties on identifier so that
repeating a query returns the same order.

Changing the chunking rules means changing `CHUNKER_VERSION` and re-chunking, since
anything derived from a chunk is invalidated by new boundaries.

## Retrieval evaluation

The regression suite runs fixed queries against a corpus built from the committed
transcript fixtures. It must never read the live archive: a suite whose corpus changes
measures the corpus rather than the retriever, and a newly published episode would move
the numbers while a green run meant nothing.

Assertions name a phrase rather than a chunk identifier, so re-chunking may move
boundaries but may not lose the passage.

Floors are raised when a change earns it and never lowered to make a failing run pass. A
floor nothing can fail is not a gate, which is why the suite also asserts that a known
weakness still measures as one.

## Observability

Honeycomb environments are deployment stages, and datasets are services. The environment
is selected by the ingest key, the dataset by `service.name`.

| | Selected by | Values |
| --- | --- | --- |
| Environment | the ingest API key | `dev`, `prod`, later `ci` |
| Dataset | `service.name` | `rag-api`, `rag-ingestion` |

Do not give a component its own environment. Traces cannot span environments, and the
services here share a database and libraries, so a component split would cut traces in
half. Filter on `service.name` for component isolation instead.

Every app names itself in `configure_tracing()`. Spans carry `service.version` from the
commit and `deployment.environment.name` from the stack, so a trace identifies both what
ran and which build produced it. Keys are per stack, in
`/rag/<stack>/honeycomb-api-key`, so a new stack reaches a new environment on its own.

CI does not export telemetry. The unit job needs no network, and every run would spend
events against the quota.

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

## Commit messages

Say what changed and why, in the imperative. Do not prefix a subject with a phase label,
and do not reference issue numbers in the subject or the body. Pull request descriptions
are where issues get linked, and they stay accurate as the roadmap moves.

Do not add a co-author trailer.

## Pull requests

Open pull requests as drafts. Do not merge without an explicit go-ahead.

Squash merges append the pull request number to the subject, which puts an issue
reference into history. Pass the subject explicitly to keep it out:

```
gh pr merge <n> --squash --delete-branch --subject "Add transcript chunking"
```

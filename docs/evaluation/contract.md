# Evaluation contract

What this system claims to answer, and how we will know whether it does.

Written before any retrieval exists, so the numbers here are targets rather than
measurements. Issue #9 replaces the provisional floors with values taken from a real
baseline. Until then, no floor in this document is evidence that anything works.

## Files

| File | Role |
| --- | --- |
| `classes.toml` | Question classes, whether each is expected to need the graph, quality floors. Read with stdlib `tomllib`. |
| `examples.jsonl` | Development and held-out examples, one JSON object per line. |
| `../../src/test_evaluation_contract.py` | Fails CI if an example drifts from a declared class or a class loses a split. |

## Corpus

The Dwarkesh Podcast archive, ingested from the post pages. Transcripts carry explicit
speaker labels and, in most episodes, per-turn timestamps, so speaker attribution is
parsed rather than inferred.

Two properties of the source were confirmed against a 12-episode sample and shape the
examples below:

- Turn headers come in four markup variants: a bare bolded name, a name with an inline
  timestamp, a name wrapped in a further span, and a name followed by a line break and
  the turn's own words in the same paragraph. Matching the structure of the paragraph
  rather than the exact markup handles all four.
- Timestamps are present in some episodes and absent in others, so a segment's start time
  is optional rather than missing data.
- Pages carry the whole transcript a second time, below the comments, inside an embedded
  script. Parsing stops at the discussion section, which removes the copy exactly. No
  content-level deduplication is needed, and none is done: identical short turns are
  common and legitimate.

## Corpus coverage

Measured across the whole archive by running the parser over every episode and comparing
the words it extracts against the word count the publisher reports.

| | Episodes |
| --- | --- |
| Produce a transcript | 87 of 133 |
| Refused, no speaker turns found | 43 |
| Refused, transcript collapsed into too few turns | 3 |

The refusals are concentrated in two groups: narrations and essays published under the
podcast type, which carry no dialogue at all, and episodes from 2021 to 2023 whose pages
use an older layout this parser does not read. Both are quarantined rather than stored
empty or partial.

Every episode the examples below depend on parses cleanly, extracting between 92 and 97
percent of the published word count, the remainder being sponsor and introduction copy.

Four episodes parse into plausible turns but recover only 28 to 60 percent of their
words. They are usable but incomplete, and they are not among the episodes the examples
depend on.

## Question classes

Six classes, each with a stance on whether it should need the graph. That stance is a
prediction, and #9 is what tests it.

| Class | Graph expected | Why |
| --- | --- | --- |
| `direct_retrieval` | no | One passage answers it. The control group. |
| `cross_episode_synthesis` | no | Wider retrieval should reach the passages. |
| `speaker_comparison` | no | Speaker is a column, so this is a metadata filter. |
| `topic_evolution` | yes | Needs topic identity across paraphrase, plus date ordering. |
| `agreement_disagreement` | yes | Needs a stance relation, not just topical proximity. |
| `bounded_multi_hop` | yes | The middle entity is never named in the question. |

Three classes are predicted to work without a graph. If all six turn out to work without
one, phases 5 through 7 have no mandate and should not be built.

## Quality floors

Provisional. Defaults in `classes.toml`, overridden per class:

- Recall@10 against the annotated episodes.
- Groundedness: every factual sentence traceable to retrieved evidence.
- Citation precision: cited spans actually support the sentence citing them.
- Metadata-filter correctness where the class depends on a filter.
- p95 latency and per-query cost.

Two invariants are not negotiable and do not get a threshold:

1. A factual answer without a transcript citation is a failure, whatever it scores.
2. A question the corpus cannot answer must produce an insufficient-evidence response.
   `stance-004` exists to catch fabricated dissent specifically.

## Retrieval regression

`retrieval_regression.jsonl` holds fixed queries run on every pull request against the two
committed transcripts, guarding against silent loss of retrieval quality. It is a
regression gate, not a measure of retrieval quality: ten queries over two episodes says
nothing about recall on the real corpus.

Measured on that frozen corpus:

| | Recall@1 | Recall@3 | Recall@10 |
| --- | --- | --- | --- |
| Postgres full text | 0.40 | 0.90 | 1.00 |
| BM25 | 0.90 | 0.90 | 1.00 |

The gap at rank one is term-rarity weighting, which Postgres ranking does not have.

## Splits

`dev` is for building. `heldout` is for release gates and never for prompt tuning. They
are separated by the `split` field, and the CI test asserts every class has both.

Twenty-four examples is a starting contract, not a finished dataset. It is enough to
detect a broken class and not enough to rank two similar configurations. #9 grows it.

## Non-goals

Out of scope, and answering these is a bug rather than a feature:

- Audio or video: no clip retrieval, no speech, no tone or delivery.
- Anything a guest said outside the podcast, including their papers and other interviews.
- Events after the most recently ingested episode.
- Corpus-wide counting and aggregation ("how many times has X come up"), which needs
  complete ingestion to be meaningful and will be confidently wrong before then.
- Whole-episode summarization.
- Advice, predictions, or opinions in the system's own voice.
- Any claim not traceable to a transcript span.

## Harbor Hub

Not yet registered. Publishing pushes these datasets to an external service, so it waits
on your explicit go-ahead, and the hub's write tools are disabled in this environment.
The files are versioned in git meanwhile, which is what the CI test enforces.

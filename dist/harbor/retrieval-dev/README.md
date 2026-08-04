# walkerhughes/retrieval-dev

Retrieval evaluation questions over the Dwarkesh Podcast archive, dev split,
12 tasks.

Generated from `docs/evaluation/examples.jsonl` by `make harbor-package`. The examples
are the source of truth and this package is disposable: regenerate it rather than
editing it.

Each task gives a question and asks for a prose answer plus the episodes and speakers it
rests on. The reward is the mean of episode recall and speaker recall against the
annotated citations, and zero when the prose answer is missing. An example that annotates
no episodes is one the corpus cannot answer, and there any citation scores zero. Answer
quality, groundedness, and latency are not scored here.

The task image ships no corpus. The dataset measures an agent that brings its own access
to the transcripts.

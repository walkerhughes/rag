# Answer a question about the Dwarkesh Podcast archive

What bottlenecks to scaling compute are described across episodes?

Write your answer to `/app/answer.json` as a single JSON object:

```json
{
  "answer": "<what the transcripts say, in prose>",
  "episodes": ["<episode slug>"],
  "speakers": ["<speaker name>"]
}
```

`episodes` are the slugs of the episodes your answer rests on, as they appear in the
dwarkesh.com URL. `speakers` are the people who said what you are reporting. List every
episode and speaker the answer depends on, and no others. If the transcripts do not
answer the question, say so in `answer` and cite nothing.

The reward is how much of the annotated episode and speaker set your citations recover.
The prose answer must be present and non-empty; its wording is not scored.

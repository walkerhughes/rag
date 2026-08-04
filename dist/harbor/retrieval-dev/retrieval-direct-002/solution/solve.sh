#!/bin/bash
# The oracle answer, so a run with the oracle agent proves the verifier scores a
# correct answer rather than proving only that the package builds.
set -euo pipefail

mkdir -p "$(dirname /app/answer.json)"
cp /solution/answer.json /app/answer.json

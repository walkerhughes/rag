#!/bin/bash
# Scores the agent's answer. A crashed verifier is a zero rather than a missing reward.
set -u

REWARD_DIR=/logs/verifier
mkdir -p "$REWARD_DIR"

if ! python3 /tests/verify.py "$REWARD_DIR/reward.txt"; then
    echo 0 > "$REWARD_DIR/reward.txt"
fi

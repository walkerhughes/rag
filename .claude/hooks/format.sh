#!/bin/sh
# Formats Python files right after Claude edits them. Reads the hook payload with
# python3, which a Python repo always has, rather than jq, which it may not.
set -eu

file=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')

case "$file" in
*.py) ;;
*) exit 0 ;;
esac

cd "$CLAUDE_PROJECT_DIR"

# Import sorting only: a bare --fix also strips imports that nothing uses yet.
# Every other lint finding is left for CI to report.
uv run ruff check --select I --fix -q "$file" || true
uv run ruff format -q "$file"

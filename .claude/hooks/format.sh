#!/bin/sh
# Formats Python files right after Claude edits them, so what reaches CI already matches
# `ruff format`. Uses python3 rather than jq: this is a Python repo, so python3 is
# guaranteed present and jq is not.
set -eu

file=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')

case "$file" in
*.py) ;;
*) exit 0 ;;
esac

cd "$CLAUDE_PROJECT_DIR"

# Import sorting only. A bare `--fix` also strips unused imports, which deletes an import
# added moments before the line that uses it. Every other lint finding is CI's to report.
uv run ruff check --select I --fix -q "$file" || true
uv run ruff format -q "$file"

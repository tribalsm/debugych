#!/bin/sh
# Start only this project's local stack after read-only checks.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
command -v python3 >/dev/null 2>&1 || { echo 'Python 3 is required for the preflight. See docs/quickstart.md' >&2; exit 1; }
PROJECT=${DEBUGYCH_LOCAL_PROJECT:-debugych-local}
python3 scripts/preflight.py --project "$PROJECT"
exec docker compose --project-name "$PROJECT" -f docker-compose.yml up --build -d --wait

#!/bin/bash
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Finder may not inherit a Homebrew shell PATH. Prefer the user's configured Node.
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
if ! command -v node >/dev/null 2>&1; then
  echo 'Node.js 22+ is required. Install it from https://nodejs.org/ and retry.' >&2
  exit 1
fi
exec node "$SCRIPT_DIR/start-local.mjs" "$@"

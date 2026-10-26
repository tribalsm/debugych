#!/bin/bash
set -eu
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! /bin/bash "$APP_DIR/scripts/start-local.sh" --reuse-backend --open "$@"; then
  echo
  echo 'See docs/macos.md. Press Enter to close.'
  read -r ignored || true
  exit 1
fi

#!/bin/sh
# Fixed project scope. Never prune, reset a daemon, or stop foreign services.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${DEBUGYCH_SERVER_ENV:-/etc/debugych/production.env}
cd "$ROOT"
dc() { docker compose --project-name debugych-server --env-file "$ENV_FILE" -f docker-compose.yml -f infra/server/compose.yml "$@"; }
case "${1:-health}" in
 validate)
  python3 scripts/server-config-check.py "$ENV_FILE"
  dc config --quiet
  ;;
 up)
  sh "$0" validate
  docker info --format '{{json .Runtimes}}' | grep -q '"runsc"' || { echo 'gVisor runtime missing; refusing startup' >&2; exit 1; }
  dc build api worker token-init runner supervisor sandbox-image playwright-image
  docker run --rm --runtime=runsc --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 32 --memory 96m --cpus 0.5 debugych-sandbox:local python -c 'print("runsc smoke passed")'
  dc up -d --no-build postgres redis token-init sandbox-image playwright-image supervisor runner api worker
  ;;
 stop) dc stop worker api supervisor runner redis postgres ;;
 health)
  dc ps
  curl --fail --silent --max-time 5 http://127.0.0.1:18080/healthz
  df -h /var/lib/docker
  ;;
 backup)
  DEST=${2:?Specify an absolute private backup directory}
  case "$DEST" in /*) ;; *) echo 'Absolute backup path required' >&2; exit 1;; esac
  umask 077
  mkdir -p "$DEST"
  test ! -e "$DEST/database.dump" && test ! -e "$DEST/projects.tar.gz"
  # Consistent point-in-time snapshot; stop only this application's writers.
  trap 'dc start api worker >/dev/null' EXIT INT TERM
  dc stop worker api
  dc exec -T postgres pg_dump -U debugych -d debugych -Fc > "$DEST/database.dump"
  IMAGE=$(dc images -q api | head -1)
  docker run --rm --network none --read-only --entrypoint tar -v debugych-server_project-data:/data:ro "$IMAGE" -C /data -czf - . > "$DEST/projects.tar.gz"
  (cd "$DEST" && sha256sum database.dump projects.tar.gz > SHA256SUMS)
  if test -f SOURCE_COMMIT; then cat SOURCE_COMMIT; else git rev-parse HEAD; fi > "$DEST/source-commit"
  echo 'Backup written to a private directory. Credentials are excluded.'
  ;;
 *) echo 'Usage: serverctl.sh validate|up|stop|health|backup /private/path' >&2; exit 2 ;;
esac

#!/usr/bin/env bash
# Trusted Linux host setup, never run in the API or a job container.
# Registers runsc and restarts Docker. Requires administrator privileges.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo 'Run with sudo on the Linux Docker host.' >&2
  exit 1
fi
command -v docker >/dev/null
apt-get update -qq
apt-get install -y ca-certificates curl gnupg
curl -fsSL https://gvisor.dev/archive.key | gpg --dearmor --yes -o /usr/share/keyrings/gvisor-archive-keyring.gpg
printf 'deb [arch=%s signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main\n' "$(dpkg --print-architecture)" > /etc/apt/sources.list.d/gvisor.list
apt-get update -qq
apt-get install -y runsc
runsc install
systemctl restart docker
if ! command -v docker-compose >/dev/null; then
  install -m 755 "$(dirname "$0")/docker-compose" /usr/local/bin/docker-compose
fi
docker run --rm --runtime=runsc --network=none --user=10000:10000 python:3.12-slim python -c 'import os; assert os.getuid()==10000; print("gVisor non-root smoke passed")'

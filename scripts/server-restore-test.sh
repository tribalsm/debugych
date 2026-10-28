#!/bin/sh
# Restore into an isolated database/volume. Does not overwrite the live stack.
set -eu
BACKUP=${1:?Specify backup directory}
API_IMAGE=${2:?Specify reviewed API image ID}
PROJECT=debugych-restore-$(date +%s)-$$
DB=$PROJECT-db
DATA=$PROJECT-data
umask 077
SECRET=$(mktemp)
python3 -c 'import secrets; print("POSTGRES_PASSWORD="+secrets.token_urlsafe(32))' > "$SECRET"
cleanup() { docker rm -f "$DB" >/dev/null 2>&1 || true; docker volume rm "$DATA" "$PROJECT-pg" >/dev/null 2>&1 || true; rm -f "$SECRET"; }
trap cleanup EXIT INT TERM
(cd "$BACKUP" && sha256sum -c SHA256SUMS)
docker volume create "$DATA" >/dev/null
docker volume create "$PROJECT-pg" >/dev/null
docker run -d --name "$DB" --network none --env-file "$SECRET" -e POSTGRES_USER=debugych -e POSTGRES_DB=debugych -v "$PROJECT-pg:/var/lib/postgresql/data" postgres:16-alpine >/dev/null
for attempt in $(seq 1 60); do
 if docker exec "$DB" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U debugych -d debugych -Atc "SELECT 1"' >/dev/null 2>&1; then break; fi
 sleep 1
done
docker exec -i "$DB" pg_restore -U debugych -d debugych --exit-on-error --no-owner < "$BACKUP/database.dump"
# The archive was made by the trusted backup command; no user-provided tar archives.
docker run --rm --network none --read-only --user 0:0 --entrypoint tar -v "$DATA:/data" -i "$API_IMAGE" -C /data -xzf - < "$BACKUP/projects.tar.gz"
docker exec "$DB" psql -U debugych -d debugych -Atc 'SELECT count(*) FROM projects; SELECT count(*) FROM records;'
docker run --rm --network none --read-only --entrypoint python -v "$DATA:/data:ro" "$API_IMAGE" -c 'from pathlib import Path; print("Restored project files:",sum(p.is_file() for p in Path("/data").rglob("*")))'
echo 'Restore completed in isolated temporary volumes; live data untouched.'

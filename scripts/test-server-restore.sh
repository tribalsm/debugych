#!/bin/sh
# Entirely synthetic database and source fixture. No live volumes are read.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
API_IMAGE=${1:-files-pasted-by-the-user-software-api:latest}
NAME=debugych-backup-fixture-$$
OUT=$(mktemp -d)
umask 077
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; docker volume rm "$NAME-pg" "$NAME-data" >/dev/null 2>&1 || true; rm -rf -- "$OUT"; }
trap cleanup EXIT INT TERM
python3 - "$OUT" <<'PY'
from pathlib import Path
import sys,secrets
p=Path(sys.argv[1]); password=secrets.token_urlsafe(32)
(p/'db.env').write_text('POSTGRES_PASSWORD='+password+'\nPOSTGRES_USER=debugych\nPOSTGRES_DB=debugych\n')
(p/'api.env').write_text('DATABASE_URL=postgresql+psycopg://debugych:'+password+'@127.0.0.1:5432/debugych\nDATA_DIR=/data\n')
PY
docker volume create "$NAME-pg" >/dev/null
docker volume create "$NAME-data" >/dev/null
docker run -d --name "$NAME" --network none --env-file "$OUT/db.env" -v "$NAME-pg:/var/lib/postgresql/data" postgres:16-alpine >/dev/null
for attempt in $(seq 1 60); do if docker exec "$NAME" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U debugych -d debugych -Atc "SELECT 1"' >/dev/null 2>&1; then break; fi; sleep 1; done
docker run --rm -i --network "container:$NAME" --env-file "$OUT/api.env" -v "$NAME-data:/data" --entrypoint python "$API_IMAGE" - <<'PY'
from apps.api.db import Base,engine,Session,Project,add_record
from pathlib import Path
Base.metadata.create_all(engine)
with Session() as db:
 p=Project(name='Synthetic restore fixture',demo=False);db.add(p);db.flush();add_record(db,p.id,'requirement',{'key':'R1','text':'Fixture only'});db.commit()
Path('/data/fixture.txt').write_text('debugych restore fixture\n')
PY
docker exec "$NAME" pg_dump -U debugych -d debugych -Fc > "$OUT/database.dump"
docker run --rm --network none --read-only --entrypoint tar -v "$NAME-data:/data:ro" "$API_IMAGE" -C /data -czf - . > "$OUT/projects.tar.gz"
(cd "$OUT" && sha256sum database.dump projects.tar.gz > SHA256SUMS)
sh "$ROOT/scripts/server-restore-test.sh" "$OUT" "$API_IMAGE"
echo 'PASS: independent PostgreSQL and file backup restored to separate temporary volumes.'

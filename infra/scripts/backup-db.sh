#!/usr/bin/env bash
#
# Dump the database to a compressed file and prune old dumps.
#
# The Docker volume survives ordinary deploys, but it is a single copy on a
# single machine: it does not survive `docker compose down -v`, a corrupted
# volume, or losing the host. Run this from cron; see DEPLOY.md.
#
# Usage:  ./infra/scripts/backup-db.sh [destination-dir]

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

DEST="${1:-${BACKUP_DIR:-/srv/backups/textroute}}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

set -a
# shellcheck disable=SC1091
. ./.env
set +a

mkdir -p "$DEST"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$DEST/textroute-$stamp.sql.gz"

docker compose -f docker-compose.prod.yml exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$target"

# A dump that failed midway can still leave a small file behind, so fail loudly
# rather than silently rotating good backups out in favour of a broken one.
if [ ! -s "$target" ]; then
    echo "error: dump is empty, removing $target" >&2
    rm -f "$target"
    exit 1
fi

find "$DEST" -name 'textroute-*.sql.gz' -type f -mtime "+$KEEP_DAYS" -delete

echo "Wrote $target"

#!/usr/bin/env sh
set -eu

: "${PGHOST:?Set PGHOST}"
: "${PGDATABASE:?Set PGDATABASE}"
: "${PGUSER:?Set PGUSER}"
: "${PGPASSWORD:?Set PGPASSWORD}"

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="${BACKUP_DIR}/hiop-${STAMP}.dump"

umask 077
mkdir -p "${BACKUP_DIR}"
pg_dump --format=custom --no-owner --no-acl --file="${FILE}" "${PGDATABASE}"
sha256sum "${FILE}" > "${FILE}.sha256"
find "${BACKUP_DIR}" -type f -name 'hiop-*.dump' -mtime "+${RETENTION_DAYS}" -delete
find "${BACKUP_DIR}" -type f -name 'hiop-*.dump.sha256' -mtime "+${RETENTION_DAYS}" -delete
echo "Backup completed: ${FILE}"

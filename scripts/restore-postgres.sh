#!/usr/bin/env sh
set -eu

: "${PGHOST:?Set PGHOST}"
: "${PGDATABASE:?Set PGDATABASE}"
: "${PGUSER:?Set PGUSER}"
: "${PGPASSWORD:?Set PGPASSWORD}"
: "${RESTORE_FILE:?Set RESTORE_FILE to a verified custom-format backup}"

if [ "${CONFIRM_RESTORE:-}" != "RESTORE_HIOP" ]; then
  echo "Restore refused. Set CONFIRM_RESTORE=RESTORE_HIOP after confirming downtime and a rollback backup." >&2
  exit 2
fi

test -f "${RESTORE_FILE}"
if [ -f "${RESTORE_FILE}.sha256" ]; then
  sha256sum --check "${RESTORE_FILE}.sha256"
fi

pg_restore --clean --if-exists --no-owner --no-acl --exit-on-error --dbname="${PGDATABASE}" "${RESTORE_FILE}"
echo "Restore completed. Run Alembic upgrade and application smoke checks before reopening traffic."

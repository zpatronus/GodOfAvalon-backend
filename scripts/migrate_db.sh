#!/bin/bash
# Manual database migration for a schema-changing deploy.
#
# Run this on the server after you `git pull`, inside the backend checkout.
# It backs up the existing db.sqlite3 to backups/ and rebuilds an empty database
# with the current schema. Then restart the service yourself as usual.
#
#   ./scripts/migrate_db.sh

set -euo pipefail

PYTHON="${GOA_PYTHON:-.venv/bin/python}"

echo "[migrate] Backing up old database and rebuilding with the current schema..."
"$PYTHON" manage.py reset_db
echo "[migrate] Done. Restart the service when ready."
#!/bin/sh
# Backend gate. Fail-fast: the first failing step stops the run.
#
# Expects a reachable PostgreSQL via POSTGRES_* and runs against the test
# database, never a developer's own data.
set -eu

cd "$(dirname "$0")/../backend"

echo "==> ruff"
ruff check .

echo "==> django check"
python manage.py check --fail-level WARNING

echo "==> migration drift"
# Fails if a model change was made without generating the migration.
python manage.py makemigrations --check --dry-run

echo "==> pytest"
pytest tests/

echo "backend checks passed"

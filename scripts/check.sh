#!/usr/bin/env bash
# The full gate, as CI runs it. Brings up a disposable PostgreSQL, runs the
# backend and frontend checks, then tears the containers down.
#
#   ./scripts/check.sh
#
# Uses its own compose project and no named volume, so it cannot touch the
# database or data belonging to `docker compose up`.
set -euo pipefail

cd "$(dirname "$0")/.."

cleanup() {
  # --volumes removes only this test project's anonymous volumes.
  docker compose -f compose.test.yaml down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== backend ==="
docker compose -f compose.test.yaml run --rm --build check

echo
echo "=== frontend ==="
docker compose -f compose.test.yaml run --rm check-frontend

echo
echo "all checks passed"

#!/bin/sh
# Frontend gate. Fail-fast.
set -eu

cd "$(dirname "$0")/../frontend"

echo "==> npm ci"
# ci, not install: installs exactly what package-lock.json pins and fails if
# package.json and the lockfile disagree.
npm ci

echo "==> eslint"
npm run lint

echo "==> typecheck"
npm run typecheck

echo "==> vitest"
npm run test -- --run

echo "==> build"
npm run build

echo "frontend checks passed"

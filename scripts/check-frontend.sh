#!/bin/sh
# Frontend gate, for running on the host.
#
# The containerised gate does NOT use this script: it builds the `check` stage
# of infra/Dockerfile.frontend, which copies the source into the image. Running
# npm ci through a bind mount would rewrite the developer's node_modules with
# the container's platform binaries. This script is here for when you want the
# same sequence against your own toolchain.
#
# Fail-fast.
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

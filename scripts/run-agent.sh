#!/usr/bin/env bash
# Optional launcher for resuming an agent session (see AUTOMATION.md).
#
# This is execution infrastructure, NOT the application's background-job
# feature. The selected stretch item is the export worker, which runs as its
# own Compose service.
#
# What this does:
#   - takes a non-blocking lock so two runs can never overlap
#   - exits immediately, without editing anything, once PROGRESS.json says the
#     work is complete
#   - runs the agent in the foreground and holds the lock for the whole
#     invocation; the launched process must not detach
#   - records the exit status
#
# What it deliberately does not do: remove a "stale" lock while a process still
# holds it, or guess your agent's CLI flags. Set AGENT_CMD yourself.
#
# Usage:
#   AGENT_CMD="your-agent --non-interactive --prompt-file AGENT_PROMPT.md" \
#     ./scripts/run-agent.sh
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

STATE_DIR="$REPO/.agent-runs"   # gitignored
LOCK="$STATE_DIR/agent.lock"
LOG="$STATE_DIR/runner.log"
mkdir -p "$STATE_DIR"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

if ! command -v flock >/dev/null 2>&1; then
  log "flock is unavailable; refusing to run without overlap protection"
  exit 1
fi

exec 9>"$LOCK"
if ! flock --nonblock 9; then
  # Another invocation is still running. This is the normal outcome for a
  # schedule that fires faster than the work completes.
  log "another run holds the lock; exiting without doing anything"
  exit 0
fi

# Completed means completed: no edits, no commits, no further launches.
if [ -f PROGRESS.json ] && python3 - <<'PY'
import json, sys
try:
    with open("PROGRESS.json") as handle:
        status = json.load(handle).get("overall_status", "")
except Exception:
    sys.exit(1)
sys.exit(0 if status in {"complete", "completed"} else 1)
PY
then
  log "PROGRESS.json reports the work complete; exiting. Disable the schedule."
  exit 0
fi

if [ -z "${AGENT_CMD:-}" ]; then
  log "AGENT_CMD is not set; nothing to launch. See AUTOMATION.md."
  exit 1
fi

log "starting: $AGENT_CMD"
# Foreground, so the lock covers the entire invocation.
# shellcheck disable=SC2086
$AGENT_CMD >>"$LOG" 2>&1
STATUS=$?
log "finished with exit status $STATUS"
exit "$STATUS"

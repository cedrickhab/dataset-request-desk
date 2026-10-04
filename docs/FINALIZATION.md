# Dataset Request Desk finalization — 2026-10-04

## Scope

Continued the existing Freebuff/OpenCode working tree; no project restart,
dependency additions, commit, push, deployment, database reset or volume removal.
The dark/amber layout, outline icons, account popover and existing business
workflows were retained. No approved images existed under `design/`, so this
pass follows the written specification and makes no screenshot-match claim.

Completed the API-backed quality chart and repaired the unfinished tests.
The chart uses Good/Usable/Bad series, shared counts and a crosshair, Kigali
7/30/90-day windows, an accessible summary and a daily table. Single-date data
renders points; zero days and unavailable history remain distinct. Range
changes no longer show the previous range's data under the new selection.
Touch selections survive finger lift. Small-count axes avoid duplicate rounded
labels. The canvas uses its CSS box and disconnects its resize observer.
Mobile artwork has space below the branding text, and hidden table content
is contained so it cannot widen the page. Zero pipeline counts have zero width.

`BUSINESS_TIME_ZONE` already defaulted to `Africa/Kigali`. The new endpoint
uses local midnight bounds and timezone-aware PostgreSQL day aggregation.
Its permission is `IsStaff`; clients and anonymous sessions are refused.
Migration `desk.0003_episode_episode_imported_at` adds the import-time index
and was confirmed applied locally. The pre-existing analytics report retains
its recording-date/UTC contract.

## Check evidence

Commands run from the repository root unless a directory is specified:

| Command | Result |
| --- | --- |
| `docker compose -f compose.test.yaml run --rm --build check` | Exit 0: Ruff, Django checks, migration drift, **246 PostgreSQL tests** passed |
| `npm run lint` in `frontend` | Exit 0 on final source |
| `npm run typecheck` in `frontend` | Exit 0 on final source |
| `npm run test -- --run` in `frontend` | Exit 0: **49 tests**, 6 files passed on final source |
| `docker compose up -d --build` | Exit 0; existing volume retained |
| `docker compose up -d --build --no-deps web` | Exit 0 after final UI fixes; includes TypeScript and Vite production build |
| `docker compose exec -T api python manage.py showmigrations desk` | Exit 0; migration 0003 applied |

Initial failures were retained as failures, then addressed: an unsorted Python
import, an `unknown` TypeScript accumulator, ambiguous dashboard selectors,
an assertion before async chart data arrived, and incorrect fixture expectations
about invalid rows and unavailable history. Test import timestamps are pinned
only in the isolated test database. Production records were never backdated.

Container Vitest runs also exceeded existing timeouts under resource contention.
The runner now uses one jsdom worker; assertions, isolation and timeouts were
not relaxed. A subsequent final-source host run passed all 49 tests. The host
runner and Chrome initially hit sandbox `spawn EPERM`; authorized executions
outside that process restriction succeeded. The final production bundle emits
one non-fatal size warning: the main chunk is about 312.7 kB (97.6 kB gzip),
slightly above the existing 300 kB warning threshold. The threshold is unchanged.

## Local review

```powershell
docker compose up -d --build
docker compose ps
```

Open **http://localhost:8080** and select a public demo row, then Sign in.
Current import history consists of one real import date, so the quality chart
correctly shows points instead of fabricated historical curves. The original
database contained 172 episodes, 11 requests and 15 assignments before this pass.
Browser evidence and the local Playwright script live under ignored
`.agent-runs/`; they are local review artifacts, not a new installed dependency
or a permanent browser test suite.

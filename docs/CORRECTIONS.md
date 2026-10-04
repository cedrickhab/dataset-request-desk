# Correction review

Source: [original brief](../reference/WORK_TASK.md), sections 2–8. The correction
image was not available in this session; the repository prototype is the visual
reference. This checklist distinguishes code inspection from executed validation.

| Requirement | Initial finding | Implementation / evidence |
|---|---|---|
| Python API, relational schema, migrations | Implemented | `backend/desk/models.py`, `backend/*/migrations/`, `backend/desk/views.py` |
| Session auth, server roles, per-client isolation | Implemented | `backend/accounts/{authentication,permissions,views}.py`, `desk/views.py:visible_requests`, `tests/test_auth.py` |
| Request workflow, actors and history | Implemented | `desk/services/workflow.py`, `tests/test_workflow.py` |
| Exclusive good/usable allocations, count-based delivery | Implemented | `desk/services/assignments.py`, `desk/models.py`, `tests/test_assignments.py` |
| Repeatable messy CSV import and reporting | Implemented | `desk/services/csv_import.py`, `management/commands/import_episodes.py`, `tests/test_import.py`, supplied `seed/episodes.csv` |
| Date-window SQL analytics | Implemented | `desk/services/analytics.py`, `tests/test_analytics.py`; README describes scale tradeoffs |
| Health and structured request logs | Implemented | `config/middleware.py`, `config/logging_formatters.py`, `tests/test_operability.py` |
| Client/operator React flows and admin user controls | Implemented | `frontend/src/pages/{Requests,RequestDetail,Episodes,Analytics,Users}.tsx` |
| Compose migrations, accounts, API and frontend | Implemented | `compose.yaml`, `management/commands/seed_users.py`; shell line endings needed correction on Windows |
| One-command automated checks | Implemented | `scripts/check.sh`, `compose.test.yaml`, backend tests and frontend component tests |
| Background export stretch | Optional, chosen and implemented | `services/exports.py`, `run_export_worker.py`, `tests/test_exports.py`, `RequestDetail.tsx` |
| CI | Optional, implemented | `.github/workflows/ci.yml` |
| Real-time push / public deployment stretches | Optional, not selected | No additions planned |
| Reproducible populated demo | Missing initially; correction added | `seed_demo_data.py`, seed registry migration, `tests/test_demo_seed.py` |
| Compact login / account popover / footers | Missing initially; implemented | `Login.tsx`, `AccountPopover.tsx`, `Shell.tsx`, `styles/app.css` |
| NOTES at 1–2 pages with supported claims | Missing initially (too long); condensed | `NOTES.md` covers the six original topics and identifies AI assistance |

The worker starts after successful `init`, claims jobs with a lease/token,
retries random failures within a bounded budget, and persists statuses.
Request detail polls active exports every three seconds. Assignment creates the
job transactionally; neither seed code nor UI simulates successful completion.
Job states remain distinct from request statuses. Delivery depends on allocation
count, including when an export fails. No videos or download artifacts are made.

Scope additions relative to the brief: opt-in populated demos, compact demo
selector, account disclosure and footers are requested corrections. Existing
task matching, in-progress-only assignment changes, first-delivery median,
last-admin guard and API import UI are implementation policies/features beyond
the minimum brief. No additional stretch is selected.

## Executed validation (4 October 2026)

- `docker compose -f compose.test.yaml run --rm --build check`: Ruff, Django
  checks, migration drift and **226 PostgreSQL tests passed**. Initial Windows
  CRLF script failure was repaired with `.gitattributes`; two new lint findings
  were fixed before the successful gate.
- In `frontend`: `npm ci`, `npm run lint`, `npm run typecheck`,
  `npm run test -- --run` (**40 passed**) and `npm run build` passed. The build
  retains a non-failing 301.33 kB main-chunk warning. Vite subprocesses required
  running outside the filesystem sandbox. Initial TypeScript and test-lint
  findings were fixed before this pass.
- `docker compose up --build --detach --wait --wait-timeout 300` succeeded on
  the existing local volume. The test suite applies migrations to a fresh test
  database; the local browser stack was **not** a fresh database.
- Both documented demo commands were run against that stack. Import found
  existing metadata: 0 imported, 189 skipped (174 duplicates, 2 conflicts,
  13 invalid), 2 blank rows. Seed: 10 requests created, then 0 created / 10
  skipped on rerun. The 14 live export jobs completed: 11 on attempt one and
  3 on attempt two. The worker remained enabled; no deterministic simulator
  was used outside tests and no database volume was deleted.
- Headless Chrome via locally installed Playwright verified full login fit at
  **1366×768 and 1920×1080**, all five demo selectors filling without submission,
  bad-password feedback, and reachable controls with scrolling in a short desktop
  window. A 683×384 CSS viewport checked the reflow equivalent of 200% zoom on
  1366×768; this was viewport emulation, not an OS browser-zoom measurement.
- Chrome verified admin Users/Analytics access; operator/client navigation;
  authenticated account name/email/role disclosure, optional organisation,
  keyboard activation, panel focus, Escape focus restoration, Tab to Sign out,
  click-outside dismissal and logout. Populated dashboards used the live API;
  **empty dashboard responses were mocked** to exercise staff import/client
  request links without deleting local data.
- Through the real UI/API: malformed CSV header feedback, supplied CSV import
  report, client request creation, count-gated delivery, staff allocation,
  live export polling to completion, client rejection, staff rework/redelivery,
  acceptance and seven history entries with actors. Client B received 404 for
  client A's validation request. That clearly labelled, accepted validation
  request remains in the local demo account, in addition to the ten seed requests.
- `.env` is ignored and untracked; only `.env.example` is tracked. The supplied
  metadata CSV was already tracked and remains unchanged. Docker context now
  excludes environment files. `git diff --check` passed.

The user clarified **desktop web only**, superseding phone-size validation.
An early narrow-window check did not pass; no phone/browser support claim is made.
Existing responsive rules are preserved. No screen-reader audit, large-volume
benchmark, real-time stretch or deployment stretch was performed. Browser evidence
and scratch scripts are local under ignored `.agent-runs/`; committed unit tests
cover account interactions, selectors, API totals and export polling.

CI is checked after pushing the final correction commit; a remote failure cannot
cancel a push that has already happened. The final handoff reports the exact SHA
and observed CI outcome.

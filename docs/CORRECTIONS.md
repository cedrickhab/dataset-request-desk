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
| Compact login / account popover / footers | Missing initially; corrections in progress | `Login.tsx`, `Shell.tsx`, `styles/app.css` |
| NOTES at 1–2 pages with supported claims | Missing initially (too long) | Rewrite during documentation pass |

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

Validation results will be recorded here after execution.

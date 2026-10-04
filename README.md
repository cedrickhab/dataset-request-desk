# Dataset Request Desk

Internal platform for a robotics data-collection company. Clients submit
dataset requests, operations staff fulfil them by assigning recorded episodes,
and clients accept or reject the delivery. Replaces a spreadsheet.

Episode **metadata** only — no video files are stored, served or downloadable
anywhere in this system.

- **Backend:** Python 3.12, Django 5.2 LTS, Django REST Framework, PostgreSQL 17
- **Frontend:** React 19, TypeScript, Vite
- **Auth:** Django sessions, HttpOnly cookies, CSRF. No tokens in browser storage.
- **Stretch item chosen:** background work — simulated per-episode export jobs
  with durable retries (see [Export simulation](#export-simulation))

---

## Run it

**Prerequisites:** Docker with Compose v2. Nothing else — Python and Node run
inside the images.

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY and POSTGRES_PASSWORD. Generate a key with:
#   python3 -c "import secrets; print(secrets.token_urlsafe(64))"

docker compose up --build
```

Then open **http://localhost:8080**.

That one command starts PostgreSQL, applies migrations, seeds the demo
accounts, and starts the API, the export worker and nginx serving the built
frontend. Ordering is handled by health and completion conditions, so there
are no sleeps to tune: migrations and seeding run in a one-shot `init`
container that must exit successfully before the API and worker start.

Set `WEB_PORT` in `.env` if 8080 is taken.

To stop while keeping local data:

```bash
docker compose down
```

### Seed accounts

Created by the `init` container on first start. These are demo credentials for
reviewing the app; they are the only credentials shown in the UI.

| Email | Password | Role |
|---|---|---|
| `admin@example.com` | `admin123` | admin |
| `ops1@example.com` | `ops123` | operator |
| `ops2@example.com` | `ops123` | operator |
| `client-a@example.com` | `client123` | client (Acme Robotics) |
| `client-b@example.com` | `client123` | client (Beta Labs) |

The login screen has a button per account that fills the fields; you still
press Sign in. Re-running the seed command never resets a password, never
changes a role, and never reactivates an account an admin deactivated.

### Optional personal administrator

Set **both** of these in `.env` and the seed step creates one extra admin:

```
PERSONAL_ADMIN_EMAIL=you@example.com
PERSONAL_ADMIN_PASSWORD=<16+ chars from a password manager>
```

If either is missing the account is skipped and the demo accounts still work.
The password is read from the environment straight into Django's password
hasher. It is never logged, never written to a file, and not in this
repository. `.env` is gitignored.

### Optional populated demo

PostgreSQL data lives in the local Docker `db_data` volume. Git clone transfers
code and metadata fixtures, **not that volume or its requests and assignments**.
Compose automatically migrates and seeds accounts only. Importing episodes alone
does not create client requests or allocations.

After startup, explicitly opt in:

```bash
docker compose exec api python manage.py import_episodes /app/seed/episodes.csv
docker compose exec api python manage.py seed_demo_data
```

The second command also reuses the supplied CSV importer, so it is safe if the
first import has already run. On an untouched demo it creates ten requests:
submitted, in progress, delivered, accepted and rejected for each of the two
public demo clients. Each asks for two `pick cup` episodes; in-progress examples
have one allocation and delivered examples have two (14 unique allocations in
total). These small counts use good/usable rows from the supplied CSV.

The seed registry makes reruns skip previously created requests, including ones
you subsequently changed. It reports created/skipped/conflicting records; it
does not adopt colliding identifiers, overwrite work, reset passwords, populate
personal accounts or reset the database. Changed/missing demo identities abort
before import. Reserved or conflicting episode rows are left untouched; an
unfulfillable example is rolled back and reported, while other examples proceed.
Resolve conflicts manually and rerun; do not delete your volume to seed a demo.

Assignments enqueue the normal simulated export jobs. **Their job statuses can
change while the worker runs**, including retries and final failure. Request
statuses are separate, and delivery requires enough assignments, not successful
exports. No videos or downloadable artifacts are generated. Demo population is
never an automatic default for other environments.

For handoff archives use tracked files, for example
`git archive --format=zip --output=../dataset-request-desk-handoff.zip HEAD`.
Never package the working directory wholesale: the previously shared ZIP included
`.env`. This checkout ignores and does not track it; keep it out of future ZIPs
and rotate any real credentials exposed through the earlier archive.

### A five-minute tour

1. Sign in as **client-a@example.com**. Create a request for 2 `pick cup`
   episodes with a future deadline. Sign out.
2. Sign in as **ops1@example.com**. Go to **Episodes → Import CSV** and upload
   `seed/episodes.csv`. The row-level report appears below the table. Import it
   a second time: everything is skipped, nothing is duplicated.
3. Open the client's request. **Start work**, then **Assign episodes** and pick
   two. Watch each episode's export simulation move through
   pending → processing → completed, retrying if it fails.
   **Mark as delivered** stays disabled until enough episodes are assigned.
4. Sign back in as **client-a@example.com**. **Accept** or **Reject**. A
   rejection sends it back so staff can restart work and deliver again.
5. Sign in as **client-b@example.com**: Beta Labs cannot see Acme's request at
   all.
6. As an admin, visit **Users**: create an account, change a role, deactivate
   someone. Try to demote yourself as the last admin — it is refused.

---

## Run the tests

One command, against a disposable database that cannot touch your dev data:

```bash
./scripts/check.sh
```

That runs the full gate in containers: Ruff, Django checks, migration-drift
check, the backend suite on real PostgreSQL, then npm ci, ESLint, `tsc`,
Vitest and the production build.

Either half alone:

```bash
docker compose -f compose.test.yaml run --rm --build check           # backend
docker compose -f compose.test.yaml run --rm check-frontend          # frontend
```

### What is covered

**248 tests: 216 backend, 32 frontend.** The choice of what to test follows the
brief's priorities — authorization, status transitions, assignment rules and
import idempotency — rather than chasing a coverage number.

| Area | Tests | The interesting ones |
|---|---|---|
| Authorization | 31 | cross-client access returns 404 not 403; deactivation and role changes take effect on the very next request; login is CSRF-protected; last-admin guard |
| Workflow | 31 | every invalid transition in the graph; admin cannot accept for a client; rework does not reset `first_delivered_at` |
| Assignment | 24 | **two threads on separate connections racing for one episode**; delivery cannot race a concurrent removal; all-or-nothing batches |
| CSV import | 53 | idempotency across three runs; conflict never overwrites; `NaN`/`Infinity` rejection; one bad row does not discard good rows |
| Analytics | 27 | window boundaries; even and odd medians; null not zero; a query-count guard that fails if aggregation moves into Python |
| Export jobs | 26 | stale claim token discarded; expired lease reclaimed; completed job never reruns |
| Operability | 20 | exactly one log line per request; no query string or password in logs; sanitized 503 |
| Query cost | 4 | every list endpoint stays at 4 queries when its row count grows 10x |
| Frontend | 32 | CSRF handshake; session expiry; actions driven by the server; conflict recovery |

The backend suite requires **real PostgreSQL**. The locking under test
(`SELECT FOR UPDATE`, `SKIP LOCKED`) does not exist on SQLite, so passing there
would prove nothing. Concurrency tests use `transaction=True` so each thread
gets its own connection.

Export tests inject a deterministic simulator — no test sleeps for 2–5 seconds
or depends on a 20% chance. The real timing was exercised by hand; see NOTES.md.

---

## CSV import

The same importer backs both the API and the CLI.

```bash
# CLI
docker compose exec api python manage.py import_episodes /app/seed/episodes.csv
docker compose exec api python manage.py import_episodes /app/seed/big.csv \
  --max-rows 500000 --report /tmp/issues.jsonl
```

Or **Episodes → Import CSV** in the UI, which shows the same report.

**Running it twice against the same file is safe** and is the behaviour the
brief asks for. The policy is *create-only*: an existing `episode_id` is never
overwritten, so a later corrupted export cannot rewrite good history.

Actual result on the supplied `seed/episodes.csv`:

```
processed=189  imported=172  skipped=17
  duplicate=2  conflict=2  invalid=13
blank rows=2 (counted separately, not included in processed)
```

Counts always satisfy `processed == imported + skipped` and
`skipped == duplicate + conflict + invalid`, asserted by a test. A second run
of the same file imports 0 and leaves the episode count at 172.

Every row outcome is reported with its physical line number, the episode id
where one could be read, a code and a reason. The API caps the detail list at
1000 rows and sets `issues_truncated`; the counts always cover every row, and
the CLI `--report` flag writes the complete list as JSONL.

How each case in the supplied file is handled, and why, is in
[NOTES.md](NOTES.md#import-decisions).

---

## Analytics

`GET /api/analytics?start=2026-08-01&end=2026-09-30` (staff only) returns
episodes per day per robot, request counts by status, the median
submitted-to-delivered time, and the top five tasks by good episodes.

**Semantics**, also returned in the response body so the UI cannot drift from
them:

- `start` and `end` are **inclusive calendar dates read as UTC**; the window is
  half-open `[start 00:00, end+1 day 00:00)`
- episode metrics filter `recorded_at`
- request counts cover requests **created** in the window, grouped by their
  **current** status; all five statuses are always present, including zeros
- the median covers requests **first delivered** in the window, measuring
  `created_at → first_delivered_at`. Rework does not reset it
- no deliveries in the window yields **null, not zero**
- ranges longer than 366 days are rejected with 400

Every figure is produced by a `GROUP BY` or an aggregate in PostgreSQL. The
median uses `percentile_cont(0.5) WITHIN GROUP (...)`, which has no ORM
equivalent and is the only raw SQL in the codebase — parameterized, never
string-interpolated. No endpoint loads episode or request rows into Python to
compute a statistic, and a test asserts the query count stays bounded so that
cannot regress.

### At 5 million episodes

Honest answer: **the per-day-per-robot query is the one that degrades, and it
degrades on response size before it degrades on time.** With the
`(recorded_at, robot_id)` index, a selective range stays an index scan, but the
aggregate still has to touch every matching row — a 90-day window over 5M
episodes is roughly 1.2M rows per scan, and the daily grid itself grows to
`days × robots` rows in the response.

What I would change, in order:

1. **Cap the range in the product, not just the API.** 366 days is already
   generous for an operational dashboard.
2. **A daily rollup table** — `(day, robot_id, quality, count)`, written by a
   nightly job or a trigger. Turns the common case from millions of rows into
   hundreds. The top-tasks and daily queries both become trivial; only
   same-day figures need the live table.
3. **A partial index** on good-quality episodes for the top-tasks query, if
   `EXPLAIN ANALYZE` on real data justifies it.
4. **Partition `desk_episode` by month** on `recorded_at` — but only with
   evidence, since it complicates the unique constraint on `episode_id`.

I have not measured any of this at 5M rows, so there are no timings here I
cannot back up. `seed/generate_episodes.py` produces a large clean file if you
want to try it.

---

## Export simulation

The chosen stretch item. On assignment, each episode gets a durable export job
that sleeps 2–5 seconds and fails 20% of the time, retrying up to 3 attempts
with 2s/4s backoff. Per-episode status appears in the request detail table.

There is **no artifact and no download** — the point is to demonstrate durable
asynchronous work, not to fake a file.

A dedicated `worker` container polls job rows in the same PostgreSQL database.
No Redis and no Celery: for a system this size the extra moving parts cost more
than they save. The trade-off is poll latency and a wasted query when idle,
which is a real limitation and is written up in NOTES.md.

Three properties make it safe:

- **Claim, then sleep, then settle.** The claim is a short transaction using
  `SELECT ... FOR UPDATE SKIP LOCKED` that writes a lease and a fresh claim
  token, then commits. The simulated sleep happens with **no transaction and no
  row lock held**, so a 5-second export never blocks the API or another worker.
- **Lease-based recovery.** A worker killed mid-sleep leaves a lease that
  expires; another worker reclaims the job, with attempts still counting so a
  crash loop cannot retry forever.
- **Token-guarded completion.** The final write only applies if the row still
  carries our claim token. A resumed worker whose lease expired finds no match
  and discards its result rather than overwriting whoever took over.

Removing an assignment deletes its job, and a worker mid-sleep on that job
discards its result rather than resurrecting a removed link.

**Export status does not gate delivery** — delivery depends on the assigned
count alone. That is a deliberate MVP policy, not an oversight: jobs here
simulate processing, and letting a simulated failure block a real delivery
would be the wrong trade.

Verified against the running stack: with the worker stopped, six assignments
queued durably as `pending`; on restart all six completed, and the random
failure genuinely fired — one job succeeded on its 3rd attempt, another on its
2nd.

---

## API

Prefix `/api`, JSON, UUID identifiers, ISO-8601 UTC timestamps. Errors are
`{"error": {"code", "message", "fields"?}, "request_id"}`. Lists are paginated
(`page_size` default 25, max 100).

| Method & path | Who | Notes |
|---|---|---|
| `GET /auth/csrf` | anonymous | The only anonymous endpoint. Issues a CSRF cookie so login can post. |
| `POST /auth/login` | anonymous | CSRF required. Throttled. |
| `POST /auth/logout` | any active user | 204 |
| `GET /auth/me` | any active user | |
| `GET /requests` | client: own; staff: all | `status`, `search` filters |
| `POST /requests` | client only | Owner and status come from the server |
| `GET /requests/{id}` | owner or staff | Includes `assigned_count`, `allowed_actions` |
| `GET /requests/{id}/history` | owner or staff | Read-only |
| `POST /requests/{id}/transitions` | role per step | 409 on an invalid or stale transition |
| `GET /requests/{id}/assignments` | owner or staff | Episode metadata plus export status |
| `POST /requests/{id}/assignments` | staff | All-or-nothing, max 100 per call |
| `DELETE /requests/{id}/assignments/{id}` | staff, in progress | 204 |
| `GET /episodes` | staff | `task_name`, `quality`, `available` |
| `POST /episodes/import` | staff | multipart; 10 MB and 100k row caps |
| `GET /analytics` | staff | `start`, `end` |
| `GET /users` · `POST /users` · `PATCH /users/{id}` | admin | |
| `GET /health` | any active user | 200, or 503 if the database is unreachable |
| `GET /api/schema` · `GET /api/docs` | any active user | OpenAPI, generated from the serializers |

`allowed_actions` is computed on the server for the current user and the stored
state, and the UI renders buttons from it rather than deciding for itself. The
UI still handles a 409, because state can change after the response is sent.

### Status codes

400 validation · 401 unauthenticated · 403 wrong role · 404 not found *or* not
yours · 409 workflow or allocation conflict · 413 upload too large · 429
throttled · 503 database unavailable.

**404 rather than 403 for another client's request is deliberate.** A 403 would
confirm the id exists and belongs to someone, which is more than the caller
should learn.

---

## Query cost

Every list endpoint issues a **constant 4 queries** regardless of how many rows
it returns — session, user, the pagination COUNT, and the page itself.
`/api/auth/me` is 2. Measured, not estimated:

```
GET /api/requests      (11 rows)  4 queries
GET /api/episodes      (30 rows)  4 queries
GET .../assignments    (10 rows)  4 queries
GET .../history                   4 queries
```

That is only true because the relationships are eager-loaded: the request list
`select_related`s the client and annotates `assigned_count` as one aggregate;
the assignment list `select_related`s the episode, its export job and the
assigning user; history `select_related`s the actor. Without those, each row
would add a query and a page of 25 would cost 25-100 instead of 4.

`tests/test_query_counts.py` asserts this directly — it loads one row, records
the query count, then loads ten times as many and fails if the count moved. At
10x the current row count the query count does not change; what grows is the
row data itself, which is bounded by `page_size` (default 25, max 100).

The exception is analytics, which aggregates across the whole window rather
than a page; its scaling is discussed above.

## Operability

- **`GET /health`** checks a real database round-trip. It **requires a
  session**, because the brief asks for login on everything but login.
  Container readiness therefore uses `pg_isready` inside the Docker network
  rather than opening a business endpoint to anonymous probes. A failure
  returns a sanitized 503 — the connection string, host and driver error never
  reach the client.
- **Structured logging:** exactly one JSON line per request, on success and on
  error, with method, path, status, `duration_ms`, `user_id` (null when
  anonymous) and `request_id`. The `request_id` also comes back in the
  `X-Request-ID` header so a user-reported error can be found in the logs.
  **Paths are logged without query strings**, so filter values cannot leak.
  Verified: no seed password or environment secret appears in any container log.

---

## Layout

```
backend/
  config/        settings, urls, logging, error envelope, middleware
  accounts/      custom user, permissions, authentication, admin services
  desk/          models, serializers, views
    services/    workflow, assignments, csv_import, analytics, exports
    management/  seed_users, import_episodes, run_export_worker
  tests/         212 tests
frontend/src/
  api/           typed client, CSRF handling, fetch hook
  auth/          session provider and role hooks
  components/    shell, dialog, badges, formatters
  pages/         login, dashboard, requests, detail, episodes, analytics, users
infra/           Dockerfiles, nginx config
scripts/         check.sh and the two halves of the gate
seed/            users.json, episodes.csv (supplied, unmodified)
prototype/       the approved visual specification
docs/            the implementation plan this was built from
```

Where to start reading: `backend/desk/services/` holds the business rules, and
each file there opens with a comment explaining the locking or policy decision
it implements.

---

## Not built

Listed plainly rather than left for you to discover. Reasoning in
[NOTES.md](NOTES.md).

Real video upload, storage or download · email · OTP/2FA · public registration ·
request editing after creation · real-time push (the brief asked for one
stretch item and this one is background work) · deployment · multi-tenant
organisations as an authorization boundary · password reset.

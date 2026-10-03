# Notes

## 1. Design

**Data model.** Five tables plus the user.

```
User (uuid, email unique+lowercased, name, organisation, role, is_active)
  │  role ∈ {client, operator, admin}, mutually exclusive
  │
  ├─< DatasetRequest (client FK, task_name, episodes_requested, deadline,
  │        notes, status, created_at, first_delivered_at)
  │      │
  │      ├─< StatusHistory (previous_status, new_status, actor FK, reason, created_at)
  │      │
  │      └─< Assignment (episode O2O, request FK, assigned_by FK, assigned_at)
  │                │
  │                └─1 ExportJob (status, attempts, max_attempts,
  │                        next_attempt_at, lease_until, claim_token, last_error)
  │
Episode (episode_id unique+normalized, robot_id, task_name, recorded_at,
         duration_seconds, operator_name, quality, imported_at)
```

**Where state lives: entirely in PostgreSQL.** There is no cache, no queue and
no in-memory job registry. The frontend holds no durable state — it refetches
after every mutation. That is a deliberate simplification: one place to look
when something is wrong, and no cache-invalidation bugs. Its cost is more
round-trips, which I accepted because the data volumes here are small.

**Rules live in the database where a rule must always hold.** The UNIQUE on
`Assignment.episode` is what actually guarantees one active reservation per
episode; the service layer's checks are there to produce a good error message,
not to be the enforcement. Same for the CHECK constraints on duration and the
status enums. If I had put those only in serializers, a management command or a
future second code path would quietly bypass them.

### The three hardest decisions

**(a) How "one episode, one request" is represented.**

I considered an `is_active` flag on `Assignment` with history retained, versus
deleting the row on release. A flag keeps a fuller audit trail, but then the
uniqueness rule becomes a partial unique index on `(episode) WHERE is_active`,
and every query needs the predicate. Forgetting it once reintroduces double
allocation.

I chose **rows exist only for live reservations**, so a plain
`OneToOneField(Episode)` is the constraint and it cannot be forgotten. The
price is that release history is lost — you can see a request's current
episodes, not every episode it ever held. For an MVP replacing a spreadsheet
that is the right side of the trade, and it is recoverable later by adding an
append-only `AssignmentEvent` table without touching the uniqueness rule.

**(b) Whether an admin is a superset of a client.**

The natural instinct is admin ⊃ operator ⊃ client. But the brief says an
administrator cannot accept a client's request, and that is correct on the
merits: accepting a delivery is the client's commercial decision, not an
operational one. A permission model where admin can do everything would let
staff sign off on their own work.

So **roles are mutually exclusive and admin is not a superset of client.**
Concretely: there is no `is_superuser` field on the user model at all, so there
is no flag that could bypass a role check, and `accept`/`reject` are gated on
`actor.is_client and request.client_id == actor.id`. Both the operator and the
admin case have their own test.

**(c) What the median delivery time means when a request is reworked.**

A request can be delivered, rejected, and delivered again. If the metric used
the *latest* delivery, a team could improve the number by delivering something
poor early. If it used *every* delivery, one difficult request would dominate.

I chose **`first_delivered_at`, written once and never reset**, measuring the
original submission-to-first-delivery turnaround. Rework is then visible in the
rejection count instead, where it belongs. This is the kind of definition that
causes arguments six months later, so it is written into the API response
itself (the `semantics` object) rather than living only in a doc.

---

## 2. What I left out, and the next two days

**Left out deliberately:**

- **Real-time updates.** The brief asked for one stretch item; I picked
  background work. Export status polls every 3 seconds, and only while a job is
  actually running. I am explicitly *not* calling that real-time.
- **Request editing.** No PATCH on a request. Editing `episodes_requested`
  after episodes are assigned raises real questions (does it un-deliver? does
  it release episodes?) that deserve a decision rather than a guess.
- **Assignment release history.** See decision (a).
- **Password reset and registration.** Admins create accounts. Self-service
  reset needs email, which is out of scope.
- **Organisations as an authorization boundary.** `organisation` is a label.
  Two users from the same company do not see each other's requests. Making it
  a real boundary is a schema and policy change, not a filter tweak, and the
  brief scoped authorization per-user.
- **Rate limiting beyond login.** And even the login throttle is weak — see
  below.

**With two more days:**

1. **A shared throttle cache.** The login throttle uses Django's default
   per-process cache, so with 3 gunicorn workers the real limit is 3× what it
   says. This is a genuine weakness I would fix first, with Redis or the
   database cache backend.
2. **The daily analytics rollup** from the README. It is the only part I know
   will not hold at the stated scale.
3. **A Playwright smoke test** of the three role journeys. The 32 component
   tests stub `fetch`; they would not catch a broken nginx route or a cookie
   flag that breaks only over real HTTP.
4. **Assignment release history**, as an append-only event table.
5. **Observability beyond logs** — the per-request lines are good for
   debugging one request and useless for spotting a trend.

---

## 3. Something that went wrong

**The CSRF hole on login, which I found by writing a test I expected to pass.**

I wrote a custom `CSRFSessionAuthentication` class early, on the reasoning that
DRF's `SessionAuthentication` only enforces CSRF when it finds a session user,
which would exempt the login endpoint. I overrode `enforce_csrf`, felt pleased,
and moved on.

Then the test `test_login_without_a_csrf_token_is_refused` returned **200**.
Login was accepting requests with no CSRF token at all.

Diagnosing it meant reading DRF's source rather than guessing. Two things
compound:

1. `APIView.as_view()` wraps every view in `csrf_exempt`, so Django's
   `CsrfViewMiddleware` never runs for the API at all — even though it is
   correctly listed in `MIDDLEWARE`. DRF substitutes its own check inside the
   authentication class.
2. `SessionAuthentication.authenticate()` returns `None` early when there is no
   session user, and `enforce_csrf` is called *after* that point. For an
   anonymous caller it is never reached.

So my override was real, correct, and never invoked. The middleware I was
relying on as a backstop was disabled by a decorator I had not applied. Two
layers of protection, both inactive, on the one anonymous endpoint that accepts
credentials.

The fix was to override `authenticate()` instead and enforce the token on any
unsafe method whether or not a session exists. The same investigation turned up
a second defect: DRF downgrades 401 to 403 unless the authenticator exposes an
`authenticate_header`, so every unauthenticated request was returning 403 and
hiding whether the caller was unauthenticated or merely lacked the role.

**What I take from it:** I had tested the mechanism I built rather than the
behaviour I wanted. "Is CSRF enforced on login?" is answerable; "does my
override run?" is not the same question. The test that caught this is the one
that posts to login with no token and asserts 403 — it does not know or care
how the protection is implemented, which is exactly why it worked.

A smaller one, found the same way: the request list paginated an unordered
queryset, because `annotate()` silently drops `Meta.ordering`. Rows could
repeat or vanish between pages. Django emits a warning for this, which was
scrolling past in the test output. It is now an error in `pytest.ini`.

---

## 4. Security

**Passwords.** Django's default PBKDF2 hasher, via `set_password`. No password
is logged, serialized or returned — the read serializers do not declare the
field, and a test asserts no `password` key appears in any user response.
New passwords go through Django's validators. The personal admin password is
read from a gitignored `.env` into the hasher and never written anywhere. The
seed file's demo passwords are hashed on insert like any other. The test suite
swaps in a cheap hasher for speed; production keeps the defaults.

**Sessions, not tokens.** Django sessions with `HttpOnly`, `SameSite=Lax`
cookies, and `Secure` driven by an env flag so local HTTP works without
weakening a TLS deployment. **Nothing is stored in `localStorage`** — there is
no bearer token for an XSS to steal, and the session cookie is unreadable to
script. `login()` cycles the session key, so a fixated pre-login session id is
useless. Deactivation takes effect on the user's **next request**, not at
session expiry, because `is_active` is checked per request.

**CSRF** is enforced on every unsafe method including login (section 3). The
CSRF cookie is deliberately script-readable so the SPA can echo it in a header;
it is not a credential by itself.

**Input validation** happens in serializers for shape and in the database for
invariants. The CSV importer is the largest untrusted-input surface: the upload
is capped at 10 MB by both nginx and Django and at 100k rows, parsed with the
`csv` module (never split on commas), streamed rather than read whole, and
every row is validated and reported. `Decimal('NaN')` and `Decimal('Infinity')`
are explicitly rejected — both parse fine and both would pass a naive `> 0`
check and then corrupt every aggregate downstream.

The only raw SQL is the `percentile_cont` median, and it is parameterized.
Everything else goes through the ORM.

### The two vulnerabilities I would worry about most

**(1) Cross-client data exposure through an object reference.** This is the
expensive bug in this class of system: an operations tool where most endpoints
are keyed by an id and most callers are staff who may see everything. One
endpoint that fetches by primary key and *then* checks ownership — or forgets
to — leaks another company's commercial requirements.

What I did: ownership is enforced by **narrowing the queryset**, in one
function (`visible_requests`) used by the list, detail, history, transition and
assignment endpoints. There is no code path that loads a request and then
checks who owns it, so there is no path that can forget to. A client asking for
another client's id gets **404, not 403**, so ids are not an existence oracle.
Clients have no route to the global episode inventory at all, and the
`assigned_request_id` field is nulled for non-staff. Tested per-endpoint, and
the analytics response is asserted to contain no other client's name or id.

**(2) Session and CSRF abuse.** Cookie auth means every authenticated user's
browser will attach credentials to a cross-site request automatically. A
missing CSRF check turns any page a logged-in operator visits into a way to
transition requests or create admin accounts. I shipped exactly that bug and
caught it (section 3), which is why I rate it highest after the first.
Mitigations: CSRF on all unsafe methods including login, `SameSite=Lax`,
`HttpOnly`, single-origin serving so no CORS relaxation is needed anywhere,
session rotation on login, and per-request `is_active` and role checks so a
revoked account cannot ride an old session.

Honourable mention: the login throttle is per-process and therefore weaker than
it looks with multiple workers. I would rather state that than imply the
endpoint is properly rate-limited.

---

## 5. Scale

**10× users (≈50 staff, hundreds of clients).** Mostly fine. What breaks first:

- **The export worker is a single process polling every second.** It processes
  one job at a time with a 2–5 second sleep, so throughput is roughly 0.2–0.5
  jobs/second regardless of load. At 10× assignment volume the queue grows
  without bound. The design already tolerates multiple workers safely
  (`SKIP LOCKED` plus lease and token), so the first fix is to run several
  replicas — but the polling becomes wasteful, and at that point `LISTEN/NOTIFY`
  or a real broker earns its complexity.
- **The login throttle's per-process cache**, as above.
- Not the dashboard: it is one paginated query.

**100× episodes (≈5M rows).** Covered in the README. In short: writes stay
fine, point lookups stay fine on the unique index, the assignment search stays
fine because it filters on exact normalized `task_name` with a supporting
index. **Analytics is what breaks** — the aggregates scan every matching row,
and a wide window returns a daily grid that grows with `days × robots`. The
answer is a daily rollup table, not a bigger database.

One thing that would bite before any of that: **the importer inserts row by
row, in its own savepoint per row**, which is what keeps one bad row from
discarding the good ones. That is ~190 round-trips for the seed file and would
be ~200k for a large export — minutes, not seconds. The fix is to validate in
bulk and `COPY` the clean rows, then retry the rejects individually; I kept the
simple version because correct per-row reporting mattered more than import
throughput for this brief, and I would not change it without a real file size
to aim at.

---

## 6. AI tooling

I used Claude (Claude Code) throughout: scaffolding the Django and React
projects, writing the bulk of the test suite, and drafting these notes.

What I did myself, and what matters for defending this code: the design
decisions in section 1 are mine and I can argue the alternatives. I verified
every dependency version against PyPI, npm and Docker Hub rather than accepting
what was suggested — which caught that `typescript-eslint` declares
`typescript >=4.8.4 <6.1.0`, so TypeScript 7 would have broken linting, and
that the GitHub Action majors I first wrote down were a version behind.

The CSRF bug in section 3 is the honest illustration of where the tool helped
and where it did not. The flawed `enforce_csrf` override was written
confidently and was wrong. What found it was a behavioural test and then
reading DRF's source. I would not have found it by reading the code I had just
written, and no amount of assistance substituted for running the thing and
disbelieving the result.

Every figure in this repository comes from a command I actually ran. The import
totals (189/172/17) are executed output, not the illustrative numbers from the
plan I was given. There are no performance timings here, because I did not
measure any.

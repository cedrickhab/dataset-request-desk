# Engineering notes

## Design and decisions

PostgreSQL is the source of truth. A client owns requests; episodes contain
metadata only. An assignment reserves one episode for one request, and an
append-only status history records actor and time. A separate export job belongs
to each assignment. React holds form state and refetches server data; permissions,
workflow actions and delivery eligibility are decided on the server.

Three consequential decisions:

- **Live reservations:** `Assignment.episode` is unique. Removing an assignment
  deletes that reservation and its job, avoiding a forgotten `is_active` filter.
  The tradeoff is no historical allocation audit; status history remains intact.
- **Separate roles:** admins have staff powers but cannot accept/reject on behalf
  of a client. Ownership filters return 404 for another client's request, including
  history and assignments. Organisation is a label, not a sharing boundary.
- **First delivery:** the median measures submission to first delivery, not later
  rework. Request counts use current status for requests created in the window;
  episode metrics use recording time. Dates are inclusive UTC calendar dates and
  no deliveries produces null. These semantics are returned by the API.

Task matching and in-progress-only allocation changes are explicit implementation
policies beyond the brief's minimum assignment rules. Delivery requires enough
allocated episodes; simulated job completion never gates it. Accepted/delivered
allocations remain reserved. The chosen stretch is background work only: a
PostgreSQL worker claims with short locks, a lease and a token, sleeps outside the
transaction, then settles only its own claim. Random failures retry within a
bounded budget. UI polling is not a real-time stretch. No video artifacts exist.

## Import decisions

The shared CLI/API importer normalizes identifiers, whitespace, task and quality
labels; it validates known robots, required fields, finite positive duration up
to 3,600 seconds, and recording timestamps. Naive timestamps mean UTC. First
valid occurrence wins: identical rows skip; different content for an existing ID
is reported and never overwrites it. Bad-quality metadata remains useful for
analytics but cannot be allocated. Row errors do not discard other valid rows.
The supplied CSV and idempotency are exercised through this importer in tests.

Opt-in demo population adds ten small requests for the two public clients using
normal workflow and assignment services. A narrowly scoped registry prevents
repeat requests/history/jobs and preserves subsequent user changes. Identifier,
account and episode collisions are reported without adopting existing work.
Seed job states naturally change while the real worker runs. Local Docker data
is not transferred by cloning the repository.

## Simplifications and next two days

No request editing, self-service registration/password reset, email, notification
system, organisation tenancy, real-time push or public deployment. Account details
are read-only. Background processing polls PostgreSQL and currently runs one job
at a time; this is simple but adds polling overhead and limits throughput.

Next priorities would be a shared login-throttle cache (the current cache is per
process), a permanent browser smoke suite, and measured analytics query plans.
An allocation event log could follow if audit requirements justify it. These are
future work, not claimed features or additional stretches.

## What went wrong and diagnosis

During corrections, Docker could not execute the backend gate on this Windows
checkout: the shell script had CRLF endings. Normalizing scripts and setting
`*.sh text eol=lf` made the documented gate run. Inspecting the dashboard also
found that status cards counted only the first page while the total used the full
API count. Filtered API totals now supply each status without changing the grid.
Type checking caught a missing `page_size` type and an unchecked array lookup in
that change; both were fixed before the successful gate. Earlier first-person
claims about debugging and personal verification have been removed because this
review could not substantiate them.

## Security

Django hashes passwords; session cookies are HttpOnly/SameSite, with Secure
configured for TLS. No bearer credentials live in browser storage. CSRF applies
to unsafe requests including anonymous login. Deactivated users lose access on
subsequent requests. Serializers validate API input; database constraints back
allocation uniqueness, enums and counts. Imports have size/row limits and reject
non-finite numbers. Queries use ORM parameters or parameterized median SQL.

The two main concerns are cross-client object access and session/CSRF abuse.
Shared ownership-filtered querysets and endpoint tests address the first; CSRF,
session rotation, cookie settings and per-request account checks address the
second. Login throttling remains weaker across multiple worker processes.
`.env` is ignored and untracked in this checkout. The previously shared archive
included it: future archives must contain tracked files only, and exposed real
credentials should be rotated. No shared Git history was rewritten.

## Scale

At 10x usage, serial export throughput (roughly one 2–5 second job at a time)
can create a backlog. Multiple workers can use the existing `SKIP LOCKED` and
lease/token design; a broker becomes useful as polling grows. At 5M episodes,
wide-range analytics scan many rows and daily/robot results grow with days times
robots. Measure plans, introduce daily rollups, then consider indexes/partitioning.
The importer writes row by row for clear errors; large imports would benefit
from staged bulk loading. No large-volume performance benchmark was run.

## AI assistance and validation

Prior repository notes disclose Claude Code assistance with scaffolding, tests
and documentation. This correction pass used OpenAI Codex for inspection, seed
implementation, UI changes, tests and documentation. This does not establish
which decisions were personally authored or understood by the submitter.
Executed checks and remaining limitations are recorded in
[the correction review](docs/CORRECTIONS.md); it separates test evidence from
code inspection. Human review and the ability to explain the submitted code
remain necessary under the original brief.

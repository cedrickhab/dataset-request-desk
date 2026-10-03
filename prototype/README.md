# Interactive white and amber prototype
Open index.html directly in Chrome or Edge. No build step or server is required. Click a demo account BELOW the credential fields, then Sign in. Use only made-up credentials: browser storage is intentionally unencrypted.

## Try the complete scenario
1. Sign in as Acme Robotics; create a request for 2 pick cup episodes with a future deadline. Sign out.
2. Sign in as Olu Operator; open that request, Start work, Assign episodes, choose2 suitable recordings. Observe per-episode simulated processing/retry/completion. Delivery is disabled below the required count and enabled when enough are assigned. Click Mark as delivered; sign out.
3. Sign in as Acme Robotics; open your request and Accept or Reject. Reject lets staff restart work/remove/replace episodes and deliver again. Beta Labs can only see its own requests.
4. Operator Episodes: search/filter/paginate; Import CSV with sample_import.csv or original ../seed/episodes.csv. View row-level report; import again to see duplicate skips. Reserved and bad episodes cannot be selected in assignment.
5. Analytics: apply UTC date range and inspect counts, first-delivery median, top tasks, daily robot counts.
6. Admin Users: create a MADE-UP account, change roles, deactivate/reactivate. Self-deactivation/last-admin changes are blocked. Created accounts can sign in.
7. Reset demo restores the initial five accounts and records. Changes persist in this browser; logout preserves data.

## Exact limits
This is a functional browser prototype, not production software. Authentication, roles, allocation rules, import validation, analytics and simulated jobs are implemented in JavaScript and can be bypassed via developer tools. Real application must enforce them server-side using the supplied plans. No network API, secure password storage, video uploads/downloads, email, OTP, deployment or actual CI is connected. Jobs use browser timers and resume on reopening; not a durable database worker. Analytics use browser memory, not PostgreSQL. Header order fixed in CSV prototype; real importer can support order-independent validated columns. Reference screenshots inspired the split login/sidebar/topbar/table/modal structure; theme is white and amber.

Local date validation is browser-based; production uses Kigali deadline policy. CSV timestamp parser is demonstrative; production must strictly reject impossible calendar dates. No personal account/password is seeded in prototype; add locally in real app via environment.

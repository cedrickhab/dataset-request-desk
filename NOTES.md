# NOTES

## 1. Design

- Backend: Python with Django and Django REST Framework
- Database: PostgreSQL, with Django migrations for the schema
- Frontend: React with TypeScript
- Main tables: users, episodes, requests, assignments, status history and export jobs. The details are in the docs folder
- All state is in PostgreSQL. The frontend reloads from the API after each change

Hardest decisions
- Delivery rule: a request needs enough assigned episodes before it can be delivered. I lock the request row when assigning, removing and changing status so two actions cannot break the count
- Import: it only creates records and never overwrites. Duplicates are skipped and conflicts are reported, so running the same file twice changes nothing
- Export jobs: I kept the queue in PostgreSQL and did not add Celery and Redis, to keep the system small

## 2. Left out and next steps

- Left out: real video files, email, 2FA, registration, request editing, real-time updates, deployment
- Next: the system only imports CSV metadata for now. I would like to add real videos, stored in object storage with only the file location saved in the database
- Other improvements are things the team already knows about. This is an exercise

## 3. Something that went wrong

- The tests showed that login accepted requests with no CSRF token. DRF skips its own CSRF check when there is no session user. I fixed it with a custom authentication class that checks the token on every unsafe request

## 4. Security

- Passwords are hashed with Django's password hashers and are not logged
- Cookie sessions with HttpOnly and SameSite, and CSRF checks on every unsafe request
- Roles are checked on the server, and a client can only see their own requests
- Biggest worries: a missing owner check on a new endpoint, and session or CSRF abuse

## 5. Scale

- I have not tested this yet
- At 100x episodes the analytics queries will slow down on wide date ranges. I would add a daily summary table
- At 10x users I would run more API copies and move sessions to a shared cache

## 6. AI tooling

- I used AI coding tools (Claude and Freebuff) to help build the code, tests and docs
````
````
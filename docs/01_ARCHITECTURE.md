# Task 01: architecture and scaffold
Goal: create a comprehensible monorepo and runnable skeleton. Before dependency installation check official supported releases; pin compatible exact versions in Python requirements and package-lock.json, avoid unpinned latest images. Use supported Django 5.2 LTS/Python 3.12, PostgreSQL 17, Node 22 as starting major versions, verifying compatibility rather than assuming future patch versions.

Structure:
backend/config/ settings, urls, logging
backend/accounts/ custom email user, permissions, admin services
backend/desk/ models, serializers, views, services, management commands
backend/desk/services/ workflow.py assignments.py csv_import.py analytics.py exports.py
backend/tests/ behavioral tests
frontend/src/ api, auth, components, pages, styles
infra/ Dockerfiles and nginx configuration
scripts/ check, pre-push, agent runner
compose.yaml; .github/workflows/ci.yml; README.md; NOTES.md; docs/; seed/

Architecture: browser -> same-origin nginx -> React assets or /api/ Django -> PostgreSQL. Dedicated Django management-command worker polls durable job rows in the same database. Avoid Redis/Celery for this 10-hour test; document polling limits. API transaction creates assignment + job atomically. Worker must never perform its simulated sleep while holding database locks.

Bootstrap custom user model BEFORE initial migration. Define thin HTTP views, service functions with atomic transactions, serializers for validation, ORM/database constraints for integrity. Do not build generic frameworks, unnecessary microservices or repository abstractions. Document state in database; frontend caches are refreshed after mutations. Cookie auth on same origin simplifies CSRF/cookie configuration.

Create container skeleton with postgres, init, api, worker and web services. Init waits for DB, migrates/seeds once; api/worker wait for init success. At this stage worker may be a documented placeholder until task 09, never mark job functionality complete prematurely. API exposes authenticated health by task 03. Use clear errors and locked dependencies.
Gate: images build, skeleton serves UI, DB connection works, README has actual commands, no secrets tracked. Commit example: Create application structure.

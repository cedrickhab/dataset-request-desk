"""Export worker: polls the job table and processes due jobs.

Runs as its own container. Polling the database rather than adding Redis and
Celery is a deliberate trade for a project this size; the cost is poll latency
and a wasted query when idle, which is documented in NOTES.md.
"""

from __future__ import annotations

import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from desk.services import exports

logger = logging.getLogger("desk.worker")


class Command(BaseCommand):
    help = "Process simulated episode export jobs."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one job, then exit. Used by tests.",
        )
        parser.add_argument(
            "--poll-seconds",
            type=float,
            default=settings.EXPORT_WORKER_POLL_SECONDS,
            help="Idle sleep between polls.",
        )

    def handle(self, *args, **options) -> None:
        simulator = exports.RandomSimulator()

        if options["once"]:
            status = exports.process_one(simulator=simulator)
            self.stdout.write(f"processed: {status or 'no due jobs'}")
            return

        stopping = False

        def request_stop(signum, frame) -> None:  # noqa: ANN001
            # Finish the job in hand, then exit. A killed worker is safe
            # anyway: its lease expires and the job is reclaimed.
            nonlocal stopping
            stopping = True
            logger.info("worker stop requested", extra={"signal": signum})

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

        logger.info(
            "worker started",
            extra={
                "poll_seconds": options["poll_seconds"],
                "max_attempts": settings.EXPORT_MAX_ATTEMPTS,
            },
        )
        while not stopping:
            try:
                status = exports.process_one(simulator=simulator)
            except Exception:
                # One bad job must not kill the worker. The lease on whatever
                # was claimed expires and it gets retried.
                logger.exception("worker iteration failed")
                connection.close()
                status = None
            if status is None and not stopping:
                time.sleep(options["poll_seconds"])
        logger.info("worker stopped")

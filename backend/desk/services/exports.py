"""Simulated export jobs.

There is no video and no artifact. The point is to demonstrate durable
asynchronous work: a job row survives a worker crash, is picked up by exactly
one worker at a time, retries with backoff, and stops at a bounded attempt
count.

The claim/sleep/settle split is deliberate:

  1. claim   - short transaction, SELECT ... FOR UPDATE SKIP LOCKED, writes a
               lease and a fresh claim_token, then COMMITS.
  2. sleep   - happens with NO transaction and NO row lock held, so a 5 second
               simulated export never blocks the API or another worker.
  3. settle  - short transaction that writes the outcome only if the row still
               carries our claim_token.

Step 3's token check is what makes a resumed worker safe. If our lease expired
and another worker reclaimed the job, the token no longer matches and our
result is discarded rather than overwriting theirs.
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from desk.models import ExportJob, ExportStatus

logger = logging.getLogger("desk.exports")


class Simulator(Protocol):
    """Injected so tests are deterministic instead of probabilistic."""

    def duration(self) -> float: ...
    def fails(self) -> bool: ...
    def sleep(self, seconds: float) -> None: ...


@dataclass
class RandomSimulator:
    """Production behaviour: uniform 2-5s, 20% failure."""

    failure_rate: float = settings.EXPORT_FAILURE_RATE
    min_seconds: float = settings.EXPORT_MIN_SLEEP_SECONDS
    max_seconds: float = settings.EXPORT_MAX_SLEEP_SECONDS
    rng: random.Random = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = random.Random()

    def duration(self) -> float:
        return self.rng.uniform(self.min_seconds, self.max_seconds)

    def fails(self) -> bool:
        return self.rng.random() < self.failure_rate

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class ScriptedSimulator:
    """Test double: fixed outcomes, no real sleeping."""

    outcomes: list[bool]  # True = this attempt fails
    fixed_duration: float = 0.0
    slept: list[float] = None  # type: ignore[assignment]
    _index: int = 0

    def __post_init__(self) -> None:
        if self.slept is None:
            self.slept = []

    def duration(self) -> float:
        return self.fixed_duration

    def fails(self) -> bool:
        if self._index >= len(self.outcomes):
            return False
        outcome = self.outcomes[self._index]
        self._index += 1
        return outcome

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def backoff_seconds(attempts: int) -> int:
    """2s, 4s, 8s ... keyed off the attempt that just failed."""
    return 2**attempts


@dataclass(frozen=True)
class Claim:
    job_id: uuid.UUID
    claim_token: uuid.UUID
    attempts: int


def claim_next_job(*, now=None, lease_seconds: int | None = None) -> Claim | None:
    """Atomically take ownership of one due job, or return None.

    SKIP LOCKED is what lets several workers poll the same table without
    serialising on the same head row.
    """
    now = now or timezone.now()
    lease = settings.EXPORT_LEASE_SECONDS if lease_seconds is None else lease_seconds
    token = uuid.uuid4()

    with transaction.atomic():
        job = (
            ExportJob.objects.select_for_update(skip_locked=True)
            .filter(
                # Due work: never started, or waiting out a backoff whose time
                # has come, or a processing job whose worker's lease expired.
                due_filter(now)
            )
            .order_by("created_at", "id")
            .first()
        )
        if job is None:
            return None
        if job.attempts >= job.max_attempts:
            # Reclaimed after the budget was already spent: close it out
            # rather than leaving it to be picked up forever.
            job.status = ExportStatus.FAILED
            job.lease_until = None
            job.claim_token = None
            job.last_error = job.last_error or "retry budget exhausted"
            job.save(update_fields=["status", "lease_until", "claim_token", "last_error", "updated_at"])
            return None

        job.status = ExportStatus.PROCESSING
        job.attempts += 1
        job.claim_token = token
        job.lease_until = now + timedelta(seconds=lease)
        job.next_attempt_at = None
        job.save(
            update_fields=[
                "status",
                "attempts",
                "claim_token",
                "lease_until",
                "next_attempt_at",
                "updated_at",
            ]
        )
        return Claim(job_id=job.id, claim_token=token, attempts=job.attempts)


def due_filter(now) -> Q:
    """Q object for 'this job is due to run'."""
    return (
        Q(status=ExportStatus.PENDING)
        | Q(status=ExportStatus.RETRY_WAIT, next_attempt_at__lte=now)
        # Crash recovery: a processing job whose lease ran out is up for grabs.
        | Q(status=ExportStatus.PROCESSING, lease_until__lt=now)
    )


def settle_claim(claim: Claim, *, failed: bool, now=None) -> str | None:
    """Record the outcome, but only if we still hold the claim.

    Returns the new status, or None when the write was discarded because the
    job was removed or reclaimed.
    """
    now = now or timezone.now()
    with transaction.atomic():
        job = (
            ExportJob.objects.select_for_update()
            # The token is the guard. A stale worker's UPDATE matches no row.
            .filter(pk=claim.job_id, claim_token=claim.claim_token)
            .first()
        )
        if job is None:
            logger.info(
                "export claim discarded",
                extra={"job_id": str(claim.job_id), "reason": "removed_or_reclaimed"},
            )
            return None
        if job.status != ExportStatus.PROCESSING:
            return None

        if not failed:
            job.status = ExportStatus.COMPLETED
            job.completed_at = now
            job.last_error = ""
        elif job.attempts >= job.max_attempts:
            job.status = ExportStatus.FAILED
            job.last_error = "export simulation failed after the final attempt"
        else:
            job.status = ExportStatus.RETRY_WAIT
            job.next_attempt_at = now + timedelta(seconds=backoff_seconds(job.attempts))
            job.last_error = "export simulation failed; scheduled for retry"

        # Releasing the claim prevents a duplicate settle for this attempt.
        job.claim_token = None
        job.lease_until = None
        job.save(
            update_fields=[
                "status",
                "completed_at",
                "last_error",
                "next_attempt_at",
                "claim_token",
                "lease_until",
                "updated_at",
            ]
        )
        return job.status


def process_one(*, simulator: Simulator, lease_seconds: int | None = None) -> str | None:
    """Claim, simulate outside any transaction, then settle."""
    claim = claim_next_job(lease_seconds=lease_seconds)
    if claim is None:
        return None

    # No lock and no open transaction across this sleep, by construction.
    simulator.sleep(simulator.duration())
    failed = simulator.fails()

    status = settle_claim(claim, failed=failed)
    if status is not None:
        logger.info(
            "export job settled",
            extra={
                "job_id": str(claim.job_id),
                "attempt": claim.attempts,
                "status": status,
            },
        )
    return status

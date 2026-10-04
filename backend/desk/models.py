"""Domain models.

Rules that must hold regardless of which code path writes are expressed as
database constraints, not only as serializer validation:

* one active assignment per episode  -> UNIQUE on assignment.episode
* duration bounds and enum values    -> CHECK constraints
* history is append-only             -> no update path is exposed over HTTP
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Quality(models.TextChoices):
    GOOD = "good", "Good"
    USABLE = "usable", "Usable"
    BAD = "bad", "Bad"


# Only these are eligible for assignment. 'bad' episodes are still imported and
# still counted by analytics; they simply cannot be delivered to a client.
ASSIGNABLE_QUALITIES = frozenset({Quality.GOOD, Quality.USABLE})


class RequestStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    IN_PROGRESS = "in_progress", "In progress"
    DELIVERED = "delivered", "Delivered"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class ExportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    RETRY_WAIT = "retry_wait", "Waiting to retry"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class Episode(models.Model):
    """One recorded clip's metadata. No video bytes are stored anywhere."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The normalized external identifier from the recording system's export.
    # Uppercased on import, so ep-00003 and EP-00003 are the same episode.
    episode_id = models.CharField(max_length=64, unique=True)
    robot_id = models.CharField(max_length=64)
    task_name = models.CharField(max_length=120)
    recorded_at = models.DateTimeField()
    duration_seconds = models.DecimalField(max_digits=8, decimal_places=2)
    operator_name = models.CharField(max_length=150)
    quality = models.CharField(max_length=16, choices=Quality.choices)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["episode_id"]
        indexes = [
            # Analytics: per-day, per-robot counts over a recorded_at range.
            models.Index(fields=["recorded_at", "robot_id"], name="episode_recorded_robot"),
            # Assignment search: exact task + quality, paginated by id.
            models.Index(fields=["task_name", "quality", "id"], name="episode_task_quality"),
            # Quality-over-time chart: daily counts over an imported_at range.
            models.Index(fields=["imported_at"], name="episode_imported_at"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_seconds__gt=0)
                & models.Q(duration_seconds__lte=settings.EPISODE_MAX_DURATION_SECONDS),
                name="episode_duration_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(quality__in=[choice.value for choice in Quality]),
                name="episode_quality_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.episode_id


class DatasetRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # PROTECT everywhere: deactivate users, never delete them, so that history
    # and assignment attribution stay intact.
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="dataset_requests",
    )
    task_name = models.CharField(max_length=120)
    episodes_requested = models.PositiveIntegerField()
    deadline = models.DateField()
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=RequestStatus.choices, default=RequestStatus.SUBMITTED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Set once, on the first delivery only. Rework that re-delivers does not
    # move it, so the median delivery metric measures the original turnaround.
    first_delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["client", "-created_at", "-id"], name="request_client_created"),
            models.Index(fields=["status", "-created_at"], name="request_status_created"),
            models.Index(fields=["first_delivered_at"], name="request_first_delivered"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(episodes_requested__gt=0)
                & models.Q(episodes_requested__lte=100_000),
                name="request_episodes_requested_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[choice.value for choice in RequestStatus]),
                name="request_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.task_name} ({self.status})"


class DemoSeedRecord(models.Model):
    """Ownership registry for opt-in demo requests; never adopt existing work."""

    key = models.CharField(primary_key=True, max_length=100)
    request = models.OneToOneField(DatasetRequest, on_delete=models.PROTECT)

    def __str__(self):
        return self.key


class Assignment(models.Model):
    """An episode reserved for a request.

    Only live reservations are rows here. Removing an assignment deletes the
    row, which is what frees the episode; the UNIQUE on `episode` is therefore
    the real enforcement of "at most one request at a time".
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    episode = models.OneToOneField(
        Episode, on_delete=models.PROTECT, related_name="assignment"
    )
    request = models.ForeignKey(
        DatasetRequest, on_delete=models.PROTECT, related_name="assignments"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignments_made"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["assigned_at", "id"]
        indexes = [models.Index(fields=["request", "assigned_at"], name="assignment_request")]

    def __str__(self) -> str:
        return f"{self.episode_id} -> {self.request_id}"


class StatusHistory(models.Model):
    """Append-only record of who moved a request and when."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        DatasetRequest, on_delete=models.PROTECT, related_name="history"
    )
    # NULL only for the creation entry. This is the one place where NULL
    # carries real meaning distinct from "": "this request had no prior
    # status" is a different fact from "its prior status was blank", and the
    # distinction is what lets the UI render the first timeline entry
    # correctly. Hence the deliberate exception to the usual blank="" rule.
    previous_status = models.CharField(  # noqa: DJ001 - NULL means "no prior status"
        max_length=16, choices=RequestStatus.choices, null=True, blank=True
    )
    new_status = models.CharField(max_length=16, choices=RequestStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="status_changes"
    )
    reason = models.CharField(max_length=2000, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "status history"
        indexes = [models.Index(fields=["request", "created_at"], name="history_request_created")]

    def __str__(self) -> str:
        return f"{self.previous_status or '-'} -> {self.new_status}"


class ExportJob(models.Model):
    """Durable simulated export, one per assignment.

    Claiming is lease-based so a worker killed mid-sleep does not strand the
    job: once lease_until passes, another worker may reclaim it. claim_token
    makes the completion write conditional, so a resumed worker holding a stale
    lease cannot overwrite the result of whoever reclaimed its job.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.OneToOneField(
        Assignment, on_delete=models.CASCADE, related_name="export_job"
    )
    status = models.CharField(
        max_length=16, choices=ExportStatus.choices, default=ExportStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=settings.EXPORT_MAX_ATTEMPTS)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True)
    # Short, sanitized. Never a traceback: this string reaches the browser.
    last_error = models.CharField(max_length=300, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            # The worker's poll: due, unfinished jobs in creation order.
            models.Index(fields=["status", "next_attempt_at"], name="job_status_due"),
            models.Index(fields=["lease_until"], name="job_lease"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[choice.value for choice in ExportStatus]),
                name="job_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(attempts__lte=models.F("max_attempts")),
                name="job_attempts_within_max",
            ),
        ]

    def __str__(self) -> str:
        return f"export {self.status} ({self.attempts}/{self.max_attempts})"

    @property
    def is_terminal(self) -> bool:
        return self.status in {ExportStatus.COMPLETED, ExportStatus.FAILED}

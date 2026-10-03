"""Episode allocation.

Allocation is all-or-nothing per call. Lock order is fixed — request row
first, then episodes ascending by primary key — so two operators assigning
overlapping sets cannot deadlock each other.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction

from accounts.models import User
from config.errors import WorkflowConflict
from desk.models import (
    ASSIGNABLE_QUALITIES,
    Assignment,
    DatasetRequest,
    Episode,
    ExportJob,
    RequestStatus,
)


@dataclass(frozen=True)
class AssignmentResult:
    created: list[Assignment]
    existing: list[Assignment]
    assigned_count: int
    episodes_requested: int


@transaction.atomic
def assign_episodes(
    *, request_id, actor: User, episode_ids: list
) -> AssignmentResult:
    if not actor.is_staff_member:
        raise WorkflowConflict("Only operations staff can assign episodes.")
    if not episode_ids:
        raise WorkflowConflict("Select at least one episode.")

    # Collapse duplicates in the submitted list while keeping first-seen order.
    unique_ids = list(dict.fromkeys(episode_ids))
    if len(unique_ids) > settings.ASSIGNMENT_MAX_PER_CALL:
        raise WorkflowConflict(
            f"Assign at most {settings.ASSIGNMENT_MAX_PER_CALL} episodes per call."
        )

    try:
        request = DatasetRequest.objects.select_for_update().get(pk=request_id)
    except DatasetRequest.DoesNotExist as exc:
        raise WorkflowConflict("This request no longer exists.") from exc

    if request.status != RequestStatus.IN_PROGRESS:
        raise WorkflowConflict(
            "Episodes can only be assigned while a request is in progress. "
            f"This request is {request.get_status_display().lower()}."
        )

    # Sorted by pk: a stable global lock order across concurrent callers.
    episodes = list(
        Episode.objects.select_for_update()
        .filter(pk__in=unique_ids)
        .order_by("pk")
    )
    found = {episode.pk for episode in episodes}
    missing = [str(eid) for eid in unique_ids if eid not in found]
    if missing:
        raise WorkflowConflict(f"Unknown episodes: {', '.join(sorted(missing))}.")

    existing_links = {
        link.episode_id: link
        for link in Assignment.objects.select_for_update()
        .filter(episode__in=episodes)
        .select_related("request")
    }

    already_here: list[Assignment] = []
    to_create: list[Episode] = []
    for episode in episodes:
        link = existing_links.get(episode.pk)
        if link is not None:
            if link.request_id == request.pk:
                # Idempotent retry of the same selection: keep the existing
                # link and, importantly, do not enqueue a second export job.
                already_here.append(link)
                continue
            raise WorkflowConflict(
                f"{episode.episode_id} is already reserved for another request."
            )
        if episode.quality not in ASSIGNABLE_QUALITIES:
            raise WorkflowConflict(
                f"{episode.episode_id} is rated {episode.quality} and cannot be assigned."
            )
        if episode.task_name != request.task_name:
            raise WorkflowConflict(
                f"{episode.episode_id} records '{episode.task_name}', "
                f"but this request is for '{request.task_name}'."
            )
        to_create.append(episode)

    created: list[Assignment] = []
    for episode in to_create:
        try:
            link = Assignment.objects.create(
                episode=episode, request=request, assigned_by=actor
            )
        except IntegrityError as exc:
            # The UNIQUE on assignment.episode is the final authority. Reaching
            # here means a competing transaction committed between our lock
            # acquisition and this insert; the whole call rolls back.
            raise WorkflowConflict(
                f"{episode.episode_id} was reserved by another operator. Nothing was assigned."
            ) from exc
        # Same transaction as the link: there is never a committed assignment
        # without its job, and never a job for a rolled-back assignment.
        ExportJob.objects.create(assignment=link, max_attempts=settings.EXPORT_MAX_ATTEMPTS)
        created.append(link)

    total = Assignment.objects.filter(request=request).count()
    return AssignmentResult(
        created=created,
        existing=already_here,
        assigned_count=total,
        episodes_requested=request.episodes_requested,
    )


@transaction.atomic
def remove_assignment(*, request_id, assignment_id, actor: User) -> int:
    """Release one episode. Returns the request's remaining assigned count."""
    if not actor.is_staff_member:
        raise WorkflowConflict("Only operations staff can remove assignments.")

    try:
        request = DatasetRequest.objects.select_for_update().get(pk=request_id)
    except DatasetRequest.DoesNotExist as exc:
        raise WorkflowConflict("This request no longer exists.") from exc

    if request.status != RequestStatus.IN_PROGRESS:
        # Delivered and accepted work stays reserved; a client reviewing a
        # delivery must not see episodes vanish from under it.
        raise WorkflowConflict(
            "Assignments can only be removed while a request is in progress. "
            "Restart work on a rejected request first."
        )

    try:
        link = Assignment.objects.select_for_update().get(pk=assignment_id, request=request)
    except Assignment.DoesNotExist as exc:
        raise WorkflowConflict("That assignment has already been removed.") from exc

    # CASCADE drops the job row with the link. A worker mid-sleep on this job
    # finds no live row with its claim token and discards its result.
    link.delete()
    return Assignment.objects.filter(request=request).count()

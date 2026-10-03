"""Request creation and status transitions.

The transition graph:

    submitted  -> in_progress                 (staff)
    in_progress-> delivered                   (staff, needs enough assignments)
    delivered  -> accepted | rejected         (owning client only)
    rejected   -> in_progress                 (staff, rework)
    accepted   -> terminal

Every transition takes the same row lock that assignment takes, which is what
makes the "enough episodes assigned" check safe against a concurrent removal.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from config.errors import WorkflowConflict
from desk.models import Assignment, DatasetRequest, RequestStatus, StatusHistory

# (current status, target status) -> who may perform it
_STAFF = "staff"
_OWNING_CLIENT = "owning_client"

TRANSITIONS: dict[tuple[str, str], str] = {
    (RequestStatus.SUBMITTED, RequestStatus.IN_PROGRESS): _STAFF,
    (RequestStatus.REJECTED, RequestStatus.IN_PROGRESS): _STAFF,
    (RequestStatus.IN_PROGRESS, RequestStatus.DELIVERED): _STAFF,
    (RequestStatus.DELIVERED, RequestStatus.ACCEPTED): _OWNING_CLIENT,
    (RequestStatus.DELIVERED, RequestStatus.REJECTED): _OWNING_CLIENT,
}

# Action names surfaced to the UI, keyed by (status, target).
ACTION_NAMES = {
    (RequestStatus.SUBMITTED, RequestStatus.IN_PROGRESS): "start_work",
    (RequestStatus.REJECTED, RequestStatus.IN_PROGRESS): "restart_work",
    (RequestStatus.IN_PROGRESS, RequestStatus.DELIVERED): "deliver",
    (RequestStatus.DELIVERED, RequestStatus.ACCEPTED): "accept",
    (RequestStatus.DELIVERED, RequestStatus.REJECTED): "reject",
}


@dataclass(frozen=True)
class TransitionResult:
    request: DatasetRequest
    history: StatusHistory


def _actor_may(actor: User, request: DatasetRequest, who: str) -> bool:
    if who == _STAFF:
        return actor.is_staff_member
    # Owning client only. An admin is excluded by design: the brief says an
    # administrator cannot accept a client's request.
    return actor.is_client and request.client_id == actor.id


def allowed_actions(actor: User, request: DatasetRequest, assigned_count: int) -> list[str]:
    """Server-computed action list for this user and this stored state."""
    actions: list[str] = []
    for (current, target), who in TRANSITIONS.items():
        if request.status != current or not _actor_may(actor, request, who):
            continue
        if target == RequestStatus.DELIVERED and assigned_count < request.episodes_requested:
            # Deliberately omitted rather than offered-and-refused, so the UI
            # can explain the shortfall instead of showing a dead button.
            continue
        actions.append(ACTION_NAMES[(current, target)])
    if actor.is_staff_member and request.status == RequestStatus.IN_PROGRESS:
        actions.append("assign")
    return actions


@transaction.atomic
def create_request(
    *,
    client: User,
    task_name: str,
    episodes_requested: int,
    deadline,  # datetime.date
    notes: str = "",
) -> DatasetRequest:
    """Create a submitted request and its opening history entry together."""
    request = DatasetRequest.objects.create(
        client=client,
        task_name=task_name,
        episodes_requested=episodes_requested,
        deadline=deadline,
        notes=notes,
        status=RequestStatus.SUBMITTED,
    )
    StatusHistory.objects.create(
        request=request,
        previous_status=None,
        new_status=RequestStatus.SUBMITTED,
        actor=client,
    )
    return request


@transaction.atomic
def transition(
    *, request_id, actor: User, target: str, reason: str = ""
) -> TransitionResult:
    """Move a request to `target`, or raise WorkflowConflict.

    Re-reads the request under select_for_update so the decision is made on
    committed state, not on whatever the caller's UI last saw.
    """
    try:
        request = DatasetRequest.objects.select_for_update().get(pk=request_id)
    except DatasetRequest.DoesNotExist as exc:
        raise WorkflowConflict("This request no longer exists.") from exc

    who = TRANSITIONS.get((request.status, target))
    if who is None:
        raise WorkflowConflict(
            f"A {request.get_status_display().lower()} request cannot move to "
            f"{RequestStatus(target).label.lower()}."
        )
    if not _actor_may(actor, request, who):
        # 409 rather than 403: the caller may well be allowed to act on this
        # request in a different state, and leaking "wrong role" vs "wrong
        # state" separately tells an attacker more than it tells a user.
        raise WorkflowConflict("Your role cannot perform this transition.")

    if target == RequestStatus.DELIVERED:
        # Counted under the same lock the assignment service takes, so a
        # removal cannot slip in between this count and the status write.
        assigned = Assignment.objects.filter(request=request).count()
        if assigned < request.episodes_requested:
            raise WorkflowConflict(
                f"{assigned} of {request.episodes_requested} episodes assigned. "
                "Assign the remaining episodes before delivering."
            )

    previous = request.status
    request.status = target
    update_fields = ["status", "updated_at"]
    if target == RequestStatus.DELIVERED and request.first_delivered_at is None:
        request.first_delivered_at = timezone.now()
        update_fields.append("first_delivered_at")
    request.save(update_fields=update_fields)

    history = StatusHistory.objects.create(
        request=request,
        previous_status=previous,
        new_status=target,
        actor=actor,
        reason=reason,
    )
    return TransitionResult(request=request, history=history)

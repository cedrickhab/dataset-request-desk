"""Administrative user management.

The last-admin guard runs inside a transaction that locks the admin rows it is
counting. Without that lock, two admins demoting each other concurrently would
both read "2 active admins", both pass, and leave the system with none.
"""

from __future__ import annotations

import logging

from django.db import transaction

from accounts.models import Role, User
from config.errors import WorkflowConflict

logger = logging.getLogger("desk.accounts")


class LastAdminProtected(WorkflowConflict):
    default_detail = "The last active administrator cannot be demoted or deactivated."
    default_code = "last_admin_protected"


class SelfDeactivationRefused(WorkflowConflict):
    default_detail = "You cannot deactivate your own account."
    default_code = "self_deactivation"


@transaction.atomic
def create_user(
    *,
    actor: User,
    email: str,
    password: str,
    name: str,
    role: str,
    organisation: str = "",
) -> User:
    user = User.objects.create_user(
        email=email,
        password=password,
        name=name,
        role=role,
        organisation=organisation,
    )
    # Audit the actor and the change, never the password.
    logger.info(
        "user created",
        extra={
            "actor_id": str(actor.pk),
            "target_id": str(user.pk),
            "role": user.role,
        },
    )
    return user


@transaction.atomic
def update_user(
    *,
    actor: User,
    user_id,
    role: str | None = None,
    is_active: bool | None = None,
) -> User:
    """Change a role and/or active flag, enforcing the two safety rules."""
    try:
        user = User.objects.select_for_update().get(pk=user_id)
    except User.DoesNotExist as exc:
        raise WorkflowConflict("That user no longer exists.") from exc

    if is_active is False and user.pk == actor.pk:
        raise SelfDeactivationRefused()

    losing_admin = user.role == Role.ADMIN and user.is_active and (
        (role is not None and role != Role.ADMIN) or is_active is False
    )
    if losing_admin:
        # Lock every other active admin row so a concurrent demotion of one of
        # them cannot run between this count and our write.
        remaining = (
            User.objects.select_for_update()
            .filter(role=Role.ADMIN, is_active=True)
            .exclude(pk=user.pk)
            .count()
        )
        if remaining == 0:
            raise LastAdminProtected()

    changes: dict[str, object] = {}
    if role is not None and role != user.role:
        changes["role"] = role
        user.role = role
    if is_active is not None and is_active != user.is_active:
        changes["is_active"] = is_active
        user.is_active = is_active

    if changes:
        user.save(update_fields=[*changes.keys(), "updated_at"])
        logger.info(
            "user updated",
            extra={
                "actor_id": str(actor.pk),
                "target_id": str(user.pk),
                "changes": changes,
            },
        )
    return user

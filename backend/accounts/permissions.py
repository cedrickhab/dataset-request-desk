"""Role permissions, evaluated from the database on every request.

Roles are read off the user loaded for this request, never from a cached claim
in a cookie or token, so a demotion or deactivation takes effect on the user's
very next call.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsActiveAuthenticated(BasePermission):
    """Authenticated and still active.

    Django's ModelBackend already refuses an inactive user at login, but a
    session minted before deactivation would otherwise keep working until it
    expired. Checking is_active per request invalidates it immediately.
    """

    message = "Authentication is required."

    def has_permission(self, request, view) -> bool:  # noqa: ANN001
        user = request.user
        return bool(user and user.is_authenticated and user.is_active)


class IsStaff(IsActiveAuthenticated):
    """Operator or admin."""

    message = "Operator or administrator access is required."

    def has_permission(self, request, view) -> bool:  # noqa: ANN001
        return super().has_permission(request, view) and request.user.is_staff_member


class IsAdmin(IsActiveAuthenticated):
    """Admin only. No superuser flag exists on the model to bypass this."""

    message = "Administrator access is required."

    def has_permission(self, request, view) -> bool:  # noqa: ANN001
        return super().has_permission(request, view) and request.user.is_admin


class IsClient(IsActiveAuthenticated):
    """Client only.

    Used for request creation and for accept/reject. An admin is intentionally
    excluded: the brief states an administrator cannot accept a client's
    request, so admin is not a superset of client.
    """

    message = "Only client accounts can perform this action."

    def has_permission(self, request, view) -> bool:  # noqa: ANN001
        return super().has_permission(request, view) and request.user.is_client

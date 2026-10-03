"""Shared fixtures.

Tests run against real PostgreSQL. The locking and constraint behaviour under
test (SELECT FOR UPDATE, SKIP LOCKED, deferred UNIQUE violations) does not
exist on SQLite, so passing there would prove nothing.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import Role, User
from desk.models import DatasetRequest, Episode, Quality, RequestStatus, StatusHistory


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Use a cheap hasher in tests only.

    PBKDF2 at Django's default iteration count dominates the runtime of a
    suite that creates users in almost every test. Production keeps Django's
    default hashers; the assertions about hashing (stored value is not the
    plaintext, check_password round-trips) hold under any hasher.
    """
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def make_user(db):
    def _make(
        email: str,
        role: str = Role.CLIENT,
        password: str = "demo-password-123",
        name: str = "",
        is_active: bool = True,
    ) -> User:
        user = User.objects.create_user(
            email=email, password=password, role=role, name=name or email
        )
        if not is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
        return user

    return _make


@pytest.fixture
def client_a(make_user) -> User:
    return make_user("client-a@example.test", Role.CLIENT, name="Acme Robotics")


@pytest.fixture
def client_b(make_user) -> User:
    return make_user("client-b@example.test", Role.CLIENT, name="Beta Labs")


@pytest.fixture
def operator(make_user) -> User:
    return make_user("ops@example.test", Role.OPERATOR, name="Olu Operator")


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin@example.test", Role.ADMIN, name="Ada Admin")


@pytest.fixture
def api():
    """A Django test client that enforces CSRF, as a browser would.

    enforce_csrf_checks=True is the point: the default test client silently
    exempts CSRF, which would make every CSRF assertion vacuous.
    """
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def login(api):
    """Log in through the real endpoints, including the CSRF handshake."""

    def _login(user: User, password: str = "demo-password-123") -> Client:
        token = api.get("/api/auth/csrf").json()["csrf_token"]
        response = api.post(
            "/api/auth/login",
            data={"email": user.email, "password": password},
            content_type="application/json",
            headers={"x-csrftoken": token},
        )
        assert response.status_code == 200, response.content
        return api

    return _login


@pytest.fixture
def csrf(api):
    def _token() -> str:
        return api.get("/api/auth/csrf").json()["csrf_token"]

    return _token


@pytest.fixture
def make_episode(db):
    counter = {"n": 0}

    def _make(
        episode_id: str | None = None,
        task_name: str = "pick cup",
        quality: str = Quality.GOOD,
        robot_id: str = "arm-01",
        recorded_at: datetime | None = None,
        duration_seconds: str = "42.00",
        operator_name: str = "Aline",
    ) -> Episode:
        counter["n"] += 1
        return Episode.objects.create(
            episode_id=episode_id or f"EP-{counter['n']:05d}",
            robot_id=robot_id,
            task_name=task_name,
            quality=quality,
            recorded_at=recorded_at
            or datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            duration_seconds=Decimal(duration_seconds),
            operator_name=operator_name,
        )

    return _make


@pytest.fixture
def make_request(db):
    def _make(
        client: User,
        task_name: str = "pick cup",
        episodes_requested: int = 2,
        status: str = RequestStatus.SUBMITTED,
        deadline: date | None = None,
    ) -> DatasetRequest:
        instance = DatasetRequest.objects.create(
            client=client,
            task_name=task_name,
            episodes_requested=episodes_requested,
            deadline=deadline or (date.today() + timedelta(days=7)),
            status=status,
        )
        StatusHistory.objects.create(
            request=instance,
            previous_status=None,
            new_status=RequestStatus.SUBMITTED,
            actor=client,
        )
        return instance

    return _make

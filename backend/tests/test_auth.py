"""Authentication and authorization.

These are the tests that would catch a real security regression, so they assert
server behaviour only: no test here checks whether the UI hides a button.
"""

from __future__ import annotations

import pytest

from accounts.models import Role, User

pytestmark = pytest.mark.django_db


class TestLogin:
    def test_login_succeeds_and_returns_the_user_without_a_password(self, api, client_a):
        token = api.get("/api/auth/csrf").json()["csrf_token"]
        response = api.post(
            "/api/auth/login",
            data={"email": client_a.email, "password": "demo-password-123"},
            content_type="application/json",
            headers={"x-csrftoken": token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == client_a.email
        assert body["role"] == Role.CLIENT
        # No password material in the response, under any key spelling.
        assert not {"password", "password_hash"} & set(body)

    def test_login_without_a_csrf_token_is_refused(self, api, client_a):
        response = api.post(
            "/api/auth/login",
            data={"email": client_a.email, "password": "demo-password-123"},
            content_type="application/json",
        )
        # CSRF applies to login too, not only to authenticated endpoints.
        assert response.status_code == 403

    def test_login_is_case_insensitive_on_the_email(self, api, client_a):
        token = api.get("/api/auth/csrf").json()["csrf_token"]
        response = api.post(
            "/api/auth/login",
            data={"email": client_a.email.upper(), "password": "demo-password-123"},
            content_type="application/json",
            headers={"x-csrftoken": token},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "email,password",
        [
            ("client-a@example.test", "wrong-password"),
            ("nobody@example.test", "demo-password-123"),
        ],
    )
    def test_wrong_password_and_unknown_email_give_the_same_response(
        self, api, client_a, email, password
    ):
        token = api.get("/api/auth/csrf").json()["csrf_token"]
        response = api.post(
            "/api/auth/login",
            data={"email": email, "password": password},
            content_type="application/json",
            headers={"x-csrftoken": token},
        )
        assert response.status_code == 401
        # Identical wording, so the endpoint cannot be used to enumerate
        # which email addresses have accounts.
        assert response.json()["error"]["message"] == "Incorrect email or password."

    def test_deactivated_account_cannot_log_in(self, api, make_user):
        user = make_user("gone@example.test", Role.CLIENT, is_active=False)
        token = api.get("/api/auth/csrf").json()["csrf_token"]
        response = api.post(
            "/api/auth/login",
            data={"email": user.email, "password": "demo-password-123"},
            content_type="application/json",
            headers={"x-csrftoken": token},
        )
        assert response.status_code == 401

    def test_session_key_rotates_on_login(self, api, client_a):
        api.get("/api/auth/csrf")
        before = api.cookies.get("sessionid") or api.cookies.get("datasetdesk_session")
        before_value = before.value if before else None
        token = api.get("/api/auth/csrf").json()["csrf_token"]
        api.post(
            "/api/auth/login",
            data={"email": client_a.email, "password": "demo-password-123"},
            content_type="application/json",
            headers={"x-csrftoken": token},
        )
        after = api.cookies["datasetdesk_session"].value
        # A session id fixated before login is not carried forward.
        assert after != before_value


class TestAuthenticationRequired:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/auth/me",
            "/api/requests",
            "/api/episodes",
            "/api/analytics?start=2026-09-01&end=2026-09-30",
            "/api/users",
            "/health",
        ],
    )
    def test_anonymous_access_is_401(self, api, path):
        response = api.get(path)
        assert response.status_code == 401, path

    def test_csrf_endpoint_is_the_only_anonymous_route(self, api):
        response = api.get("/api/auth/csrf")
        assert response.status_code == 200
        assert "csrf_token" in response.json()


class TestRoleEnforcement:
    def test_client_cannot_list_episodes(self, login, client_a):
        session = login(client_a)
        assert session.get("/api/episodes").status_code == 403

    def test_client_cannot_read_analytics(self, login, client_a):
        session = login(client_a)
        response = session.get("/api/analytics?start=2026-09-01&end=2026-09-30")
        assert response.status_code == 403

    def test_operator_cannot_manage_users(self, login, operator):
        session = login(operator)
        assert session.get("/api/users").status_code == 403

    def test_operator_cannot_create_a_request(self, login, operator, csrf):
        session = login(operator)
        response = session.post(
            "/api/requests",
            data={
                "task_name": "pick cup",
                "episodes_requested": 1,
                "deadline": "2099-01-01",
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 403

    def test_admin_can_manage_users(self, login, admin):
        session = login(admin)
        assert session.get("/api/users").status_code == 200

    def test_admin_cannot_create_a_request_either(self, login, admin, csrf):
        """Admin is not a superset of client.

        The brief says an administrator cannot accept a client's request, so
        admin deliberately does not inherit the client role's abilities.
        """
        session = login(admin)
        response = session.post(
            "/api/requests",
            data={
                "task_name": "pick cup",
                "episodes_requested": 1,
                "deadline": "2099-01-01",
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 403

    def test_deactivation_takes_effect_on_the_next_request(
        self, login, client_a
    ):
        """An existing session stops working the moment the account is off.

        Without a per-request is_active check the session would keep working
        until it expired, which is the bug this test exists to prevent.
        """
        session = login(client_a)
        assert session.get("/api/auth/me").status_code == 200

        client_a.is_active = False
        client_a.save(update_fields=["is_active"])

        assert session.get("/api/auth/me").status_code == 401

    def test_role_change_takes_effect_on_the_next_request(self, login, client_a):
        session = login(client_a)
        assert session.get("/api/episodes").status_code == 403

        client_a.role = Role.OPERATOR
        client_a.save(update_fields=["role"])

        # Read from the database per request, not from a cached session claim.
        assert session.get("/api/episodes").status_code == 200

    def test_unsafe_method_without_csrf_is_refused_when_authenticated(
        self, login, client_a
    ):
        session = login(client_a)
        response = session.post(
            "/api/requests",
            data={
                "task_name": "pick cup",
                "episodes_requested": 1,
                "deadline": "2099-01-01",
            },
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_logout_invalidates_the_session(self, login, client_a, csrf):
        session = login(client_a)
        assert session.post("/api/auth/logout", headers={"x-csrftoken": csrf()}).status_code == 204
        assert session.get("/api/auth/me").status_code == 401


class TestUserAdministration:
    def test_admin_creates_a_user_with_a_hashed_password(self, login, admin, csrf):
        session = login(admin)
        response = session.post(
            "/api/users",
            data={
                "name": "New Operator",
                "email": "New.Operator@Example.test",
                "password": "a-long-enough-password",
                "role": Role.OPERATOR,
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 201
        created = User.objects.get(email="new.operator@example.test")
        assert created.password != "a-long-enough-password"
        assert created.check_password("a-long-enough-password")
        assert "password" not in response.json()

    def test_duplicate_email_is_rejected_case_insensitively(self, login, admin, csrf):
        session = login(admin)
        response = session.post(
            "/api/users",
            data={
                "name": "Clash",
                "email": admin.email.upper(),
                "password": "a-long-enough-password",
                "role": Role.CLIENT,
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 400
        assert "email" in response.json()["error"]["fields"]

    def test_weak_password_is_rejected(self, login, admin, csrf):
        session = login(admin)
        response = session.post(
            "/api/users",
            data={
                "name": "Weak",
                "email": "weak@example.test",
                "password": "123",
                "role": Role.CLIENT,
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 400

    def test_last_active_admin_cannot_be_demoted(self, login, admin, csrf):
        session = login(admin)
        response = session.patch(
            f"/api/users/{admin.id}",
            data={"role": Role.OPERATOR},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "last_admin_protected"
        admin.refresh_from_db()
        assert admin.role == Role.ADMIN

    def test_admin_cannot_deactivate_themselves(self, login, admin, make_user, csrf):
        # A second admin exists, so the last-admin rule is not what blocks this.
        make_user("admin2@example.test", Role.ADMIN)
        session = login(admin)
        response = session.patch(
            f"/api/users/{admin.id}",
            data={"is_active": False},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "self_deactivation"

    def test_admin_can_be_demoted_when_another_admin_remains(
        self, login, admin, make_user, csrf
    ):
        other = make_user("admin2@example.test", Role.ADMIN)
        session = login(admin)
        response = session.patch(
            f"/api/users/{other.id}",
            data={"role": Role.OPERATOR},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 200
        other.refresh_from_db()
        assert other.role == Role.OPERATOR

    def test_inactive_admin_does_not_count_toward_the_guard(
        self, login, admin, make_user, csrf
    ):
        """A deactivated admin must not keep the guard satisfied.

        Counting it would allow demoting the last *usable* admin and locking
        everyone out of user management.
        """
        make_user("dormant@example.test", Role.ADMIN, is_active=False)
        session = login(admin)
        response = session.patch(
            f"/api/users/{admin.id}",
            data={"role": Role.OPERATOR},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 409

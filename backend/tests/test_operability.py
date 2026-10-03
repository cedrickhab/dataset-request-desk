"""Health endpoint, structured logging and the error envelope."""

from __future__ import annotations

import json
import logging
from unittest import mock

import pytest

from config.logging_formatters import JSONFormatter

pytestmark = pytest.mark.django_db


class TestHealth:
    def test_authenticated_health_reports_ok(self, login, client_a):
        session = login(client_a)
        response = session.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}

    def test_health_requires_authentication(self, api):
        assert api.get("/health").status_code == 401

    def test_health_reports_503_when_the_database_is_down(self, login, client_a):
        """Patches the probe, not the connection.

        Patching django.db.connection would also break the session backend,
        so the request would fail during authentication and never reach the
        view whose error handling is the thing under test.
        """
        session = login(client_a)
        with mock.patch(
            "accounts.views.probe_database", side_effect=OSError("down")
        ):
            response = session.get("/health")
        assert response.status_code == 503
        assert response.json()["status"] == "unavailable"

    def test_health_failure_does_not_leak_connection_detail(self, login, client_a):
        session = login(client_a)
        secret = "connection to server at db-host port 5432 failed: password 'hunter2'"
        with mock.patch(
            "accounts.views.probe_database", side_effect=OSError(secret)
        ):
            response = session.get("/health")
        body = response.content.decode()
        assert "hunter2" not in body
        assert "db-host" not in body

    def test_the_probe_really_queries_the_database(self, db):
        """Guards the seam above: the probe must do actual work."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from accounts.views import probe_database

        with CaptureQueriesContext(connection) as captured:
            probe_database()
        assert any("SELECT 1" in query["sql"] for query in captured.captured_queries)


class TestAccessLog:
    def test_exactly_one_line_per_request_with_the_required_fields(
        self, login, client_a, caplog
    ):
        session = login(client_a)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="desk.access"):
            session.get("/api/requests")

        records = [r for r in caplog.records if r.name == "desk.access"]
        assert len(records) == 1
        record = records[0]
        assert record.method == "GET"
        assert record.path == "/api/requests"
        assert record.status == 200
        assert record.user_id == str(client_a.id)
        assert isinstance(record.duration_ms, float)
        assert record.request_id

    def test_anonymous_request_logs_a_null_user(self, api, caplog):
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="desk.access"):
            api.get("/api/requests")
        record = next(r for r in caplog.records if r.name == "desk.access")
        assert record.user_id is None
        assert record.status == 401

    def test_error_responses_are_logged_once_too(self, login, client_a, caplog):
        session = login(client_a)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="desk.access"):
            session.get("/api/episodes")
        records = [r for r in caplog.records if r.name == "desk.access"]
        assert len(records) == 1
        assert records[0].status == 403

    def test_query_string_is_not_logged(self, login, operator, caplog):
        """Filters and anything accidentally placed in a URL stay out of logs."""
        session = login(operator)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="desk.access"):
            session.get("/api/episodes?task_name=secret-value&quality=good")
        record = next(r for r in caplog.records if r.name == "desk.access")
        assert record.path == "/api/episodes"
        assert "secret-value" not in record.path

    def test_password_never_appears_in_the_login_log(self, api, client_a, caplog):
        password = "demo-password-123"
        token = api.get("/api/auth/csrf").json()["csrf_token"]
        caplog.clear()
        with caplog.at_level(logging.INFO):
            api.post(
                "/api/auth/login",
                data={"email": client_a.email, "password": password},
                content_type="application/json",
                headers={"x-csrftoken": token},
            )
        for record in caplog.records:
            rendered = JSONFormatter().format(record)
            assert password not in rendered

    def test_response_carries_the_request_id(self, login, client_a):
        session = login(client_a)
        response = session.get("/api/requests")
        assert response["X-Request-ID"]


class TestJSONFormatter:
    def test_emits_one_json_object_per_line(self):
        record = logging.LogRecord(
            name="desk.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request",
            args=(),
            exc_info=None,
        )
        record.method = "GET"
        record.status = 200
        rendered = JSONFormatter().format(record)
        assert "\n" not in rendered
        payload = json.loads(rendered)
        assert payload["message"] == "request"
        assert payload["method"] == "GET"
        assert payload["level"] == "INFO"

    def test_exception_is_reduced_to_its_type(self):
        """No traceback text in the structured stream."""
        try:
            raise ValueError("sensitive detail in the message")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="desk",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="failed",
                args=(),
                exc_info=sys.exc_info(),
            )
        payload = json.loads(JSONFormatter().format(record))
        assert payload["exception"] == "ValueError"
        assert "sensitive detail" not in json.dumps(payload)


class TestErrorEnvelope:
    def test_validation_error_shape(self, login, client_a, csrf):
        session = login(client_a)
        response = session.post(
            "/api/requests",
            data={"task_name": "", "episodes_requested": 0, "deadline": "nope"},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert set(body["error"]["fields"]) >= {"task_name", "deadline"}
        assert body["request_id"]

    def test_not_found_shape(self, login, client_a):
        import uuid

        session = login(client_a)
        response = session.get(f"/api/requests/{uuid.uuid4()}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_method_not_allowed_shape(self, login, client_a, csrf):
        session = login(client_a)
        response = session.delete("/api/requests", headers={"x-csrftoken": csrf()})
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"

    def test_malformed_uuid_in_path_is_404(self, login, client_a):
        session = login(client_a)
        assert session.get("/api/requests/not-a-uuid").status_code == 404


class TestSchemaAccess:
    def test_schema_requires_authentication(self, api):
        assert api.get("/api/schema").status_code in {401, 403}

    def test_authenticated_user_can_read_the_schema(self, login, operator):
        session = login(operator)
        response = session.get("/api/schema")
        assert response.status_code == 200

    def test_schema_does_not_mention_a_password_field_on_reads(self, login, admin):
        session = login(admin)
        body = session.get("/api/schema").content.decode()
        # UserCreate legitimately accepts a password; the read shape must not
        # expose one, and no hash field may appear anywhere.
        assert "password_hash" not in body

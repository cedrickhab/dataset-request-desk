"""Request lifecycle, ownership and status history."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from desk.models import DatasetRequest, RequestStatus, StatusHistory

pytestmark = pytest.mark.django_db


def _transition(session, request_id, status, csrf, reason=""):
    payload = {"status": status}
    if reason:
        payload["reason"] = reason
    return session.post(
        f"/api/requests/{request_id}/transitions",
        data=payload,
        content_type="application/json",
        headers={"x-csrftoken": csrf()},
    )


class TestCreation:
    def test_client_creates_a_submitted_request_with_history(self, login, client_a, csrf):
        session = login(client_a)
        response = session.post(
            "/api/requests",
            data={
                "task_name": "Pick Cup",
                "episodes_requested": 2,
                "deadline": (date.today() + timedelta(days=5)).isoformat(),
                "notes": "Clear view of the cup.",
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 201
        body = response.json()
        # Status and owner come from the server, never the payload.
        assert body["status"] == RequestStatus.SUBMITTED
        assert body["client_id"] == str(client_a.id)
        # Task name is normalized on the way in, so assignment matching works.
        assert body["task_name"] == "pick cup"

        instance = DatasetRequest.objects.get(pk=body["id"])
        history = list(instance.history.all())
        assert len(history) == 1
        assert history[0].previous_status is None
        assert history[0].new_status == RequestStatus.SUBMITTED
        assert history[0].actor_id == client_a.id

    def test_client_cannot_set_owner_or_status(self, login, client_a, client_b, csrf):
        """An injected owner or status is rejected, not silently dropped.

        Silently ignoring them would let a caller believe it had created a
        request for another client.
        """
        session = login(client_a)
        response = session.post(
            "/api/requests",
            data={
                "task_name": "pick cup",
                "episodes_requested": 1,
                "deadline": (date.today() + timedelta(days=5)).isoformat(),
                "client_id": str(client_b.id),
                "status": RequestStatus.ACCEPTED,
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 400
        fields = response.json()["error"]["fields"]
        assert "client_id" in fields and "status" in fields
        assert DatasetRequest.objects.count() == 0

    def test_deadline_in_the_past_is_rejected(self, login, client_a, csrf):
        session = login(client_a)
        response = session.post(
            "/api/requests",
            data={
                "task_name": "pick cup",
                "episodes_requested": 1,
                "deadline": (date.today() - timedelta(days=1)).isoformat(),
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 400
        assert "deadline" in response.json()["error"]["fields"]

    @pytest.mark.parametrize("count", [0, -1, 100_001])
    def test_episode_count_outside_1_to_100000_is_rejected(
        self, login, client_a, csrf, count
    ):
        session = login(client_a)
        response = session.post(
            "/api/requests",
            data={
                "task_name": "pick cup",
                "episodes_requested": count,
                "deadline": (date.today() + timedelta(days=5)).isoformat(),
            },
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 400


class TestOwnership:
    def test_client_sees_only_their_own_requests(
        self, login, client_a, client_b, make_request
    ):
        mine = make_request(client_a)
        make_request(client_b)
        session = login(client_a)
        body = session.get("/api/requests").json()
        assert [row["id"] for row in body["results"]] == [str(mine.id)]
        assert body["count"] == 1

    def test_delivered_list_is_client_scoped_and_orders_by_delivery_time(
        self, login, client_a, client_b, make_request
    ):
        older = make_request(client_a, status=RequestStatus.DELIVERED)
        newer = make_request(client_a, status=RequestStatus.DELIVERED)
        make_request(client_b, status=RequestStatus.DELIVERED)
        older.first_delivered_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
        older.save(update_fields=["first_delivered_at"])
        newer.first_delivered_at = datetime(2026, 10, 2, tzinfo=timezone.utc)
        newer.save(update_fields=["first_delivered_at"])

        body = login(client_a).get(
            "/api/requests?status=delivered&page_size=3"
        ).json()

        assert body["count"] == 2
        assert [row["id"] for row in body["results"]] == [
            str(newer.id),
            str(older.id),
        ]

    def test_other_clients_request_is_404_not_403(
        self, login, client_a, client_b, make_request
    ):
        """404 keeps request ids from being an existence oracle.

        A 403 here would confirm that the id is real and belongs to somebody,
        which is more than the caller is entitled to know.
        """
        theirs = make_request(client_b)
        session = login(client_a)
        assert session.get(f"/api/requests/{theirs.id}").status_code == 404
        assert session.get(f"/api/requests/{theirs.id}/history").status_code == 404
        assert session.get(f"/api/requests/{theirs.id}/assignments").status_code == 404

    def test_client_cannot_transition_another_clients_request(
        self, login, client_a, client_b, make_request, csrf
    ):
        theirs = make_request(client_b, status=RequestStatus.DELIVERED)
        session = login(client_a)
        response = _transition(session, theirs.id, RequestStatus.ACCEPTED, csrf)
        assert response.status_code == 404
        theirs.refresh_from_db()
        assert theirs.status == RequestStatus.DELIVERED

    def test_staff_sees_every_request(
        self, login, operator, client_a, client_b, make_request
    ):
        make_request(client_a)
        make_request(client_b)
        session = login(operator)
        assert session.get("/api/requests").json()["count"] == 2


class TestTransitions:
    def test_full_happy_path(
        self, login, client_a, operator, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, episodes_requested=1)
        episode = make_episode(task_name="pick cup")

        staff = login(operator)
        assert _transition(staff, instance.id, RequestStatus.IN_PROGRESS, csrf).status_code == 200
        assert staff.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        ).status_code == 201
        assert _transition(staff, instance.id, RequestStatus.DELIVERED, csrf).status_code == 200
        staff.post("/api/auth/logout", headers={"x-csrftoken": csrf()})

        owner = login(client_a)
        response = _transition(owner, instance.id, RequestStatus.ACCEPTED, csrf)
        assert response.status_code == 200
        assert response.json()["status"] == RequestStatus.ACCEPTED

        instance.refresh_from_db()
        assert instance.first_delivered_at is not None
        # Creation, start, deliver, accept.
        assert instance.history.count() == 4

    def test_reject_then_rework_then_redeliver(
        self, login, client_a, operator, make_request, make_episode, csrf
    ):
        instance = make_request(
            client_a, episodes_requested=1, status=RequestStatus.IN_PROGRESS
        )
        episode = make_episode(task_name="pick cup")
        staff = login(operator)
        staff.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        _transition(staff, instance.id, RequestStatus.DELIVERED, csrf)
        instance.refresh_from_db()
        first_delivery = instance.first_delivered_at
        staff.post("/api/auth/logout", headers={"x-csrftoken": csrf()})

        owner = login(client_a)
        assert _transition(
            owner, instance.id, RequestStatus.REJECTED, csrf, reason="Wrong angle"
        ).status_code == 200
        owner.post("/api/auth/logout", headers={"x-csrftoken": csrf()})

        staff = login(operator)
        assert _transition(staff, instance.id, RequestStatus.IN_PROGRESS, csrf).status_code == 200
        assert _transition(staff, instance.id, RequestStatus.DELIVERED, csrf).status_code == 200

        instance.refresh_from_db()
        # first_delivered_at is NOT reset by rework: the median delivery metric
        # measures the original turnaround, not the last one.
        assert instance.first_delivered_at == first_delivery

        rejection = instance.history.filter(new_status=RequestStatus.REJECTED).get()
        assert rejection.reason == "Wrong angle"

    def test_client_cannot_start_work(self, login, client_a, make_request, csrf):
        instance = make_request(client_a)
        session = login(client_a)
        response = _transition(session, instance.id, RequestStatus.IN_PROGRESS, csrf)
        assert response.status_code == 409
        instance.refresh_from_db()
        assert instance.status == RequestStatus.SUBMITTED

    def test_operator_cannot_accept_on_the_clients_behalf(
        self, login, operator, client_a, make_request, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.DELIVERED)
        session = login(operator)
        assert _transition(session, instance.id, RequestStatus.ACCEPTED, csrf).status_code == 409

    def test_admin_cannot_accept_a_clients_request(
        self, login, admin, client_a, make_request, csrf
    ):
        """Stated explicitly in the brief, so it gets its own test."""
        instance = make_request(client_a, status=RequestStatus.DELIVERED)
        session = login(admin)
        assert _transition(session, instance.id, RequestStatus.ACCEPTED, csrf).status_code == 409
        instance.refresh_from_db()
        assert instance.status == RequestStatus.DELIVERED

    @pytest.mark.parametrize(
        "current,target",
        [
            (RequestStatus.SUBMITTED, RequestStatus.DELIVERED),
            (RequestStatus.SUBMITTED, RequestStatus.ACCEPTED),
            (RequestStatus.IN_PROGRESS, RequestStatus.ACCEPTED),
            (RequestStatus.DELIVERED, RequestStatus.IN_PROGRESS),
            (RequestStatus.ACCEPTED, RequestStatus.IN_PROGRESS),
            (RequestStatus.ACCEPTED, RequestStatus.REJECTED),
            (RequestStatus.REJECTED, RequestStatus.DELIVERED),
        ],
    )
    def test_skipped_and_invalid_transitions_are_refused(
        self, login, operator, client_a, make_request, csrf, current, target
    ):
        instance = make_request(client_a, status=current)
        session = login(operator)
        response = _transition(session, instance.id, target, csrf)
        assert response.status_code == 409
        instance.refresh_from_db()
        assert instance.status == current

    def test_accepted_is_terminal_for_the_client_too(
        self, login, client_a, make_request, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.ACCEPTED)
        session = login(client_a)
        for target in (RequestStatus.REJECTED, RequestStatus.DELIVERED):
            assert _transition(session, instance.id, target, csrf).status_code == 409

    def test_delivery_blocked_below_the_requested_count(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(
            client_a, episodes_requested=3, status=RequestStatus.IN_PROGRESS
        )
        episode = make_episode(task_name="pick cup")
        session = login(operator)
        session.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        response = _transition(session, instance.id, RequestStatus.DELIVERED, csrf)
        assert response.status_code == 409
        assert "1 of 3" in response.json()["error"]["message"]

    def test_delivery_allowed_above_the_requested_count(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        """The rule is 'at least', not 'exactly'."""
        instance = make_request(
            client_a, episodes_requested=1, status=RequestStatus.IN_PROGRESS
        )
        ids = [str(make_episode(task_name="pick cup").id) for _ in range(3)]
        session = login(operator)
        session.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": ids},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert _transition(session, instance.id, RequestStatus.DELIVERED, csrf).status_code == 200

    def test_unknown_status_value_is_400_not_409(
        self, login, operator, client_a, make_request, csrf
    ):
        instance = make_request(client_a)
        session = login(operator)
        response = _transition(session, instance.id, "archived", csrf)
        assert response.status_code == 400


class TestHistoryAndActions:
    def test_history_records_actor_and_order(
        self, login, operator, client_a, make_request, csrf
    ):
        instance = make_request(client_a)
        session = login(operator)
        _transition(session, instance.id, RequestStatus.IN_PROGRESS, csrf)

        body = session.get(f"/api/requests/{instance.id}/history").json()
        assert [row["new_status"] for row in body] == [
            RequestStatus.SUBMITTED,
            RequestStatus.IN_PROGRESS,
        ]
        assert body[1]["actor_name"] == operator.name
        assert body[1]["previous_status"] == RequestStatus.SUBMITTED

    def test_history_is_read_only_over_http(
        self, login, operator, client_a, make_request, csrf
    ):
        instance = make_request(client_a)
        session = login(operator)
        response = session.post(
            f"/api/requests/{instance.id}/history",
            data={"new_status": RequestStatus.ACCEPTED},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 405
        assert StatusHistory.objects.filter(request=instance).count() == 1

    def test_failed_transition_writes_no_history(
        self, login, client_a, make_request, csrf
    ):
        """Atomicity: a refused transition must leave no trace."""
        instance = make_request(client_a)
        before = StatusHistory.objects.filter(request=instance).count()
        session = login(client_a)
        _transition(session, instance.id, RequestStatus.DELIVERED, csrf)
        assert StatusHistory.objects.filter(request=instance).count() == before

    def test_allowed_actions_are_computed_for_the_viewer(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(
            client_a, episodes_requested=1, status=RequestStatus.IN_PROGRESS
        )
        staff = login(operator)
        # No episodes assigned yet, so 'deliver' must not be offered.
        actions = staff.get(f"/api/requests/{instance.id}").json()["allowed_actions"]
        assert "assign" in actions
        assert "deliver" not in actions

        episode = make_episode(task_name="pick cup")
        staff.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        actions = staff.get(f"/api/requests/{instance.id}").json()["allowed_actions"]
        assert "deliver" in actions

    def test_client_sees_accept_and_reject_only_when_delivered(
        self, login, client_a, make_request
    ):
        pending = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        delivered = make_request(client_a, status=RequestStatus.DELIVERED)
        session = login(client_a)

        assert session.get(f"/api/requests/{pending.id}").json()["allowed_actions"] == []
        actions = session.get(f"/api/requests/{delivered.id}").json()["allowed_actions"]
        assert sorted(actions) == ["accept", "reject"]

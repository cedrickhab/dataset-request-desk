"""Episode allocation rules, including real cross-connection races."""

from __future__ import annotations

import threading
from datetime import UTC

import pytest
from django.db import connections, transaction

from config.errors import WorkflowConflict
from desk.models import (
    Assignment,
    DatasetRequest,
    Episode,
    ExportJob,
    Quality,
    RequestStatus,
)
from desk.services import assignments as service

pytestmark = pytest.mark.django_db


def _assign(session, request_id, episode_ids, csrf):
    return session.post(
        f"/api/requests/{request_id}/assignments",
        data={"episode_ids": [str(eid) for eid in episode_ids]},
        content_type="application/json",
        headers={"x-csrftoken": csrf()},
    )


class TestAssignmentRules:
    def test_assigning_creates_a_link_and_one_export_job(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(operator)

        response = _assign(session, instance.id, [episode.id], csrf)
        assert response.status_code == 201
        assert response.json()["assigned_count"] == 1
        assert Assignment.objects.filter(request=instance).count() == 1
        # The job is created in the same transaction as the link.
        assert ExportJob.objects.count() == 1

    @pytest.mark.parametrize("quality", [Quality.BAD])
    def test_bad_quality_cannot_be_assigned(
        self, login, operator, client_a, make_request, make_episode, csrf, quality
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup", quality=quality)
        session = login(operator)

        response = _assign(session, instance.id, [episode.id], csrf)
        assert response.status_code == 409
        assert "bad" in response.json()["error"]["message"]
        assert Assignment.objects.count() == 0

    def test_task_name_must_match_the_request(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(
            client_a, task_name="pick cup", status=RequestStatus.IN_PROGRESS
        )
        episode = make_episode(task_name="fold towel")
        session = login(operator)

        response = _assign(session, instance.id, [episode.id], csrf)
        assert response.status_code == 409
        assert Assignment.objects.count() == 0

    def test_episode_cannot_be_assigned_to_two_requests(
        self, login, operator, client_a, client_b, make_request, make_episode, csrf
    ):
        first = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        second = make_request(client_b, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(operator)

        assert _assign(session, first.id, [episode.id], csrf).status_code == 201
        response = _assign(session, second.id, [episode.id], csrf)
        assert response.status_code == 409
        assert "another request" in response.json()["error"]["message"]
        assert Assignment.objects.count() == 1

    def test_reassigning_the_same_episode_is_idempotent(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        """A retried submit must not create a second job for the same episode."""
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(operator)

        _assign(session, instance.id, [episode.id], csrf)
        response = _assign(session, instance.id, [episode.id], csrf)

        assert response.status_code == 200
        body = response.json()
        assert body["created_ids"] == []
        assert len(body["existing_ids"]) == 1
        assert body["assigned_count"] == 1
        assert ExportJob.objects.count() == 1

    def test_duplicate_ids_within_one_call_collapse(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(operator)

        response = _assign(session, instance.id, [episode.id, episode.id], csrf)
        assert response.status_code == 201
        assert response.json()["assigned_count"] == 1

    def test_a_batch_with_one_bad_episode_assigns_nothing(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        """All-or-nothing: a partial batch would be worse than a clear refusal."""
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        good = make_episode(task_name="pick cup")
        bad = make_episode(task_name="pick cup", quality=Quality.BAD)
        session = login(operator)

        response = _assign(session, instance.id, [good.id, bad.id], csrf)
        assert response.status_code == 409
        assert Assignment.objects.count() == 0
        assert ExportJob.objects.count() == 0

    def test_unknown_episode_id_rolls_the_whole_call_back(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        import uuid

        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        good = make_episode(task_name="pick cup")
        session = login(operator)

        response = _assign(session, instance.id, [good.id, uuid.uuid4()], csrf)
        assert response.status_code == 409
        assert Assignment.objects.count() == 0

    @pytest.mark.parametrize(
        "status",
        [
            RequestStatus.SUBMITTED,
            RequestStatus.DELIVERED,
            RequestStatus.ACCEPTED,
            RequestStatus.REJECTED,
        ],
    )
    def test_assignment_only_while_in_progress(
        self, login, operator, client_a, make_request, make_episode, csrf, status
    ):
        instance = make_request(client_a, status=status)
        episode = make_episode(task_name="pick cup")
        session = login(operator)

        assert _assign(session, instance.id, [episode.id], csrf).status_code == 409

    def test_client_cannot_assign(
        self, login, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(client_a)

        assert _assign(session, instance.id, [episode.id], csrf).status_code == 403
        assert Assignment.objects.count() == 0

    def test_over_the_per_call_limit_is_rejected(
        self, login, operator, client_a, make_request, csrf, settings
    ):
        import uuid

        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        session = login(operator)
        too_many = [uuid.uuid4() for _ in range(settings.ASSIGNMENT_MAX_PER_CALL + 1)]

        assert _assign(session, instance.id, too_many, csrf).status_code == 400


class TestRemoval:
    def test_staff_removes_an_assignment_and_frees_the_episode(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(operator)
        _assign(session, instance.id, [episode.id], csrf)
        link = Assignment.objects.get()

        response = session.delete(
            f"/api/requests/{instance.id}/assignments/{link.id}",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 204
        assert Assignment.objects.count() == 0
        # The job goes with the link, so no orphan keeps running.
        assert ExportJob.objects.count() == 0
        # And the episode is assignable again.
        assert _assign(session, instance.id, [episode.id], csrf).status_code == 201

    def test_removal_blocked_once_delivered(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        """Delivered work stays reserved while the client reviews it."""
        instance = make_request(
            client_a, episodes_requested=1, status=RequestStatus.IN_PROGRESS
        )
        episode = make_episode(task_name="pick cup")
        session = login(operator)
        _assign(session, instance.id, [episode.id], csrf)
        link = Assignment.objects.get()
        instance.status = RequestStatus.DELIVERED
        instance.save(update_fields=["status"])

        response = session.delete(
            f"/api/requests/{instance.id}/assignments/{link.id}",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 409
        assert Assignment.objects.count() == 1

    def test_removing_an_already_removed_assignment_is_409(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(operator)
        _assign(session, instance.id, [episode.id], csrf)
        link = Assignment.objects.get()
        url = f"/api/requests/{instance.id}/assignments/{link.id}"

        assert session.delete(url, headers={"x-csrftoken": csrf()}).status_code == 204
        assert session.delete(url, headers={"x-csrftoken": csrf()}).status_code == 409

    def test_client_cannot_remove(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        staff = login(operator)
        _assign(staff, instance.id, [episode.id], csrf)
        link = Assignment.objects.get()
        staff.post("/api/auth/logout", headers={"x-csrftoken": csrf()})

        owner = login(client_a)
        response = owner.delete(
            f"/api/requests/{instance.id}/assignments/{link.id}",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 403
        assert Assignment.objects.count() == 1


class TestEpisodeVisibility:
    def test_available_filter_excludes_assigned_and_bad(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        free = make_episode(task_name="pick cup")
        taken = make_episode(task_name="pick cup")
        make_episode(task_name="pick cup", quality=Quality.BAD)
        session = login(operator)
        _assign(session, instance.id, [taken.id], csrf)

        body = session.get("/api/episodes?available=true").json()
        assert [row["id"] for row in body["results"]] == [str(free.id)]

    def test_staff_sees_allocation_but_filters_are_exact_on_task(
        self, login, operator, make_episode
    ):
        make_episode(task_name="pick cup")
        make_episode(task_name="fold towel")
        session = login(operator)

        body = session.get("/api/episodes?task_name=pick cup").json()
        assert body["count"] == 1
        assert body["results"][0]["task_name"] == "pick cup"

    def test_client_has_no_route_to_the_episode_inventory(self, login, client_a):
        session = login(client_a)
        assert session.get("/api/episodes?available=true").status_code == 403

    def test_client_sees_their_own_requests_assigned_episodes(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        staff = login(operator)
        _assign(staff, instance.id, [episode.id], csrf)
        staff.post("/api/auth/logout", headers={"x-csrftoken": csrf()})

        owner = login(client_a)
        body = owner.get(f"/api/requests/{instance.id}/assignments").json()
        assert len(body["results"]) == 1
        assert body["results"][0]["episode"]["episode_id"] == episode.episode_id
        # Allocation state of the global inventory is staff-only.
        assert body["results"][0]["episode"]["assigned_request_id"] is None


@pytest.mark.django_db(transaction=True)
class TestConcurrency:
    """Real races across separate database connections.

    These use transaction=True so each thread gets its own connection and
    PostgreSQL's row locks actually apply. On SQLite they would prove nothing,
    which is why the suite requires PostgreSQL.
    """

    def test_two_threads_cannot_assign_the_same_episode(
        self, operator, client_a, client_b
    ):
        from datetime import datetime
        from decimal import Decimal

        episode = Episode.objects.create(
            episode_id="EP-RACE-1",
            robot_id="arm-01",
            task_name="pick cup",
            recorded_at=datetime(2026, 9, 1, tzinfo=UTC),
            duration_seconds=Decimal("10.00"),
            operator_name="Aline",
            quality=Quality.GOOD,
        )
        first = DatasetRequest.objects.create(
            client=client_a,
            task_name="pick cup",
            episodes_requested=1,
            deadline="2099-01-01",
            status=RequestStatus.IN_PROGRESS,
        )
        second = DatasetRequest.objects.create(
            client=client_b,
            task_name="pick cup",
            episodes_requested=1,
            deadline="2099-01-01",
            status=RequestStatus.IN_PROGRESS,
        )

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def attempt(request_id) -> None:
            try:
                barrier.wait(timeout=10)
                service.assign_episodes(
                    request_id=request_id, actor=operator, episode_ids=[episode.id]
                )
                with lock:
                    outcomes.append("ok")
            except WorkflowConflict:
                with lock:
                    outcomes.append("conflict")
            except Exception as exc:  # pragma: no cover - surfaced on failure
                with lock:
                    outcomes.append(f"error:{exc!r}")
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=(first.id,)),
            threading.Thread(target=attempt, args=(second.id,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        # Exactly one winner, and exactly one stored assignment.
        assert sorted(outcomes) == ["conflict", "ok"], outcomes
        assert Assignment.objects.filter(episode=episode).count() == 1

    def test_delivery_cannot_race_past_a_concurrent_removal(
        self, operator, client_a
    ):
        """The count check and the removal take the same request lock.

        Without that shared lock, a removal committing between the count and
        the status write would let a request be delivered under-supplied.
        """
        from datetime import datetime
        from decimal import Decimal

        from desk.services import workflow

        instance = DatasetRequest.objects.create(
            client=client_a,
            task_name="pick cup",
            episodes_requested=1,
            deadline="2099-01-01",
            status=RequestStatus.IN_PROGRESS,
        )
        episode = Episode.objects.create(
            episode_id="EP-RACE-2",
            robot_id="arm-01",
            task_name="pick cup",
            recorded_at=datetime(2026, 9, 1, tzinfo=UTC),
            duration_seconds=Decimal("10.00"),
            operator_name="Aline",
            quality=Quality.GOOD,
        )
        link = Assignment.objects.create(
            episode=episode, request=instance, assigned_by=operator
        )

        started = threading.Event()
        results: dict[str, object] = {}

        def hold_then_remove() -> None:
            """Take the request lock, signal, then remove inside the lock."""
            try:
                with transaction.atomic():
                    DatasetRequest.objects.select_for_update().get(pk=instance.pk)
                    started.set()
                    # Give the deliverer time to block on the same row.
                    import time

                    time.sleep(1.0)
                    Assignment.objects.filter(pk=link.pk).delete()
                results["removed"] = True
            finally:
                connections.close_all()

        def deliver() -> None:
            try:
                started.wait(timeout=10)
                import time

                time.sleep(0.2)
                workflow.transition(
                    request_id=instance.id, actor=operator, target=RequestStatus.DELIVERED
                )
                results["delivered"] = "ok"
            except WorkflowConflict as exc:
                results["delivered"] = f"conflict:{exc.detail}"
            finally:
                connections.close_all()

        remover = threading.Thread(target=hold_then_remove)
        deliverer = threading.Thread(target=deliver)
        remover.start()
        deliverer.start()
        remover.join(timeout=20)
        deliverer.join(timeout=20)

        instance.refresh_from_db()
        assert results.get("removed") is True
        # The deliverer waited for the lock, then saw 0 assignments and refused.
        assert str(results.get("delivered", "")).startswith("conflict")
        assert instance.status == RequestStatus.IN_PROGRESS

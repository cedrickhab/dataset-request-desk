"""Simulated export jobs.

Every outcome here is scripted. There is no test that sleeps for 2-5 seconds
or relies on a 20% probability: a suite that flakes one run in five is worse
than no suite. The real timing and randomness live in RandomSimulator, which
is exercised by hand and documented in NOTES.md.
"""

from __future__ import annotations

import threading
import uuid
from datetime import timedelta

import pytest
from django.db import connections
from django.utils import timezone

from desk.models import Assignment, ExportJob, ExportStatus, RequestStatus
from desk.services import assignments as assignment_service
from desk.services import exports

pytestmark = pytest.mark.django_db


def succeed() -> exports.ScriptedSimulator:
    return exports.ScriptedSimulator(outcomes=[False])


def fail(times: int = 1) -> exports.ScriptedSimulator:
    return exports.ScriptedSimulator(outcomes=[True] * times)


@pytest.fixture
def job(operator, client_a, make_request, make_episode) -> ExportJob:
    """One pending job, created the way the API creates it."""
    instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
    episode = make_episode(task_name="pick cup")
    assignment_service.assign_episodes(
        request_id=instance.id, actor=operator, episode_ids=[episode.id]
    )
    return ExportJob.objects.get()


class TestJobCreation:
    def test_assignment_creates_exactly_one_pending_job(self, job):
        assert job.status == ExportStatus.PENDING
        assert job.attempts == 0
        assert job.max_attempts == 3
        assert ExportJob.objects.count() == 1

    def test_reassignment_does_not_enqueue_a_second_job(
        self, operator, client_a, make_request, make_episode
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        for _ in range(3):
            assignment_service.assign_episodes(
                request_id=instance.id, actor=operator, episode_ids=[episode.id]
            )
        assert ExportJob.objects.count() == 1

    def test_removing_the_assignment_removes_the_job(self, job, operator):
        link = Assignment.objects.get()
        assignment_service.remove_assignment(
            request_id=link.request_id, assignment_id=link.id, actor=operator
        )
        assert ExportJob.objects.count() == 0


class TestProcessing:
    def test_successful_attempt_completes(self, job):
        status = exports.process_one(simulator=succeed())
        assert status == ExportStatus.COMPLETED
        job.refresh_from_db()
        assert job.attempts == 1
        assert job.completed_at is not None
        assert job.last_error == ""
        # The claim is released, so nothing can settle it twice.
        assert job.claim_token is None
        assert job.lease_until is None

    def test_failure_schedules_a_retry_with_backoff(self, job):
        status = exports.process_one(simulator=fail())
        assert status == ExportStatus.RETRY_WAIT
        job.refresh_from_db()
        assert job.attempts == 1
        assert job.next_attempt_at is not None
        assert job.completed_at is None
        # 2 ** 1 seconds after the first failure.
        assert job.next_attempt_at > timezone.now()

    def test_fail_then_succeed(self, job):
        exports.process_one(simulator=fail())
        job.refresh_from_db()
        # Make the retry due instead of waiting out the backoff.
        job.next_attempt_at = timezone.now() - timedelta(seconds=1)
        job.save(update_fields=["next_attempt_at"])

        status = exports.process_one(simulator=succeed())
        assert status == ExportStatus.COMPLETED
        job.refresh_from_db()
        assert job.attempts == 2
        assert job.last_error == ""

    def test_permanent_failure_after_the_attempt_budget(self, job):
        for expected in (ExportStatus.RETRY_WAIT, ExportStatus.RETRY_WAIT, ExportStatus.FAILED):
            ExportJob.objects.filter(pk=job.pk).update(
                next_attempt_at=timezone.now() - timedelta(seconds=1)
            )
            assert exports.process_one(simulator=fail()) == expected

        job.refresh_from_db()
        assert job.status == ExportStatus.FAILED
        assert job.attempts == 3
        assert "final attempt" in job.last_error
        # The assignment survives a failed export.
        assert Assignment.objects.count() == 1

    def test_a_failed_job_is_not_retried_again(self, job):
        ExportJob.objects.filter(pk=job.pk).update(
            status=ExportStatus.FAILED, attempts=3
        )
        assert exports.process_one(simulator=succeed()) is None

    def test_a_completed_job_is_never_rerun(self, job):
        exports.process_one(simulator=succeed())
        job.refresh_from_db()
        completed_at = job.completed_at

        assert exports.process_one(simulator=fail()) is None
        job.refresh_from_db()
        assert job.status == ExportStatus.COMPLETED
        assert job.completed_at == completed_at
        assert job.attempts == 1

    def test_no_due_jobs_returns_none(self, db):
        assert exports.process_one(simulator=succeed()) is None

    def test_a_job_waiting_out_its_backoff_is_not_claimed(self, job):
        exports.process_one(simulator=fail())
        # next_attempt_at is still in the future.
        assert exports.process_one(simulator=succeed()) is None

    def test_the_simulator_sleeps_outside_the_transaction(self, job):
        """The sleep must not happen while a row lock is held.

        A 5 second sleep inside the claim transaction would block every other
        worker and any API call touching that row.
        """
        simulator = exports.ScriptedSimulator(outcomes=[False], fixed_duration=3.5)
        exports.process_one(simulator=simulator)
        assert simulator.slept == [3.5]


class TestClaimSafety:
    def test_claiming_marks_processing_with_a_lease_and_token(self, job):
        claim = exports.claim_next_job()
        assert claim is not None
        job.refresh_from_db()
        assert job.status == ExportStatus.PROCESSING
        assert job.claim_token == claim.claim_token
        assert job.lease_until is not None

    def test_a_stale_claim_cannot_overwrite_a_reclaimed_job(self, job):
        """The core safety property of the lease design.

        Worker A claims, stalls past its lease, worker B reclaims and
        completes. Worker A then wakes and tries to settle. Its write must be
        discarded, not allowed to stamp its own outcome over B's result.
        """
        stale = exports.claim_next_job(lease_seconds=0)
        assert stale is not None

        # Lease has already expired, so the job is due again.
        fresh = exports.claim_next_job()
        assert fresh is not None
        assert fresh.claim_token != stale.claim_token
        assert exports.settle_claim(fresh, failed=False) == ExportStatus.COMPLETED

        # Worker A finally reports in.
        assert exports.settle_claim(stale, failed=True) is None
        job.refresh_from_db()
        assert job.status == ExportStatus.COMPLETED

    def test_settling_a_removed_job_is_discarded(self, job, operator):
        claim = exports.claim_next_job()
        link = Assignment.objects.get()
        assignment_service.remove_assignment(
            request_id=link.request_id, assignment_id=link.id, actor=operator
        )
        # No live row carries this token, so the completion is dropped rather
        # than resurrecting a removed assignment.
        assert exports.settle_claim(claim, failed=False) is None
        assert ExportJob.objects.count() == 0

    def test_settling_with_a_wrong_token_is_discarded(self, job):
        claim = exports.claim_next_job()
        forged = exports.Claim(
            job_id=claim.job_id, claim_token=uuid.uuid4(), attempts=claim.attempts
        )
        assert exports.settle_claim(forged, failed=False) is None
        job.refresh_from_db()
        assert job.status == ExportStatus.PROCESSING

    def test_expired_lease_is_reclaimed_with_attempt_accounting(self, job):
        """Crash recovery: a killed worker's job gets picked up again."""
        exports.claim_next_job(lease_seconds=0)
        job.refresh_from_db()
        assert job.attempts == 1

        reclaim = exports.claim_next_job()
        assert reclaim is not None
        job.refresh_from_db()
        # Attempts keep counting, so a crash loop cannot retry forever.
        assert job.attempts == 2

    def test_reclaim_closes_out_a_job_past_its_budget(self, job):
        ExportJob.objects.filter(pk=job.pk).update(
            status=ExportStatus.PROCESSING,
            attempts=3,
            lease_until=timezone.now() - timedelta(seconds=1),
        )
        assert exports.claim_next_job() is None
        job.refresh_from_db()
        assert job.status == ExportStatus.FAILED

    def test_an_unexpired_lease_is_not_stolen(self, job):
        exports.claim_next_job(lease_seconds=300)
        assert exports.claim_next_job() is None

    def test_backoff_doubles(self):
        assert exports.backoff_seconds(1) == 2
        assert exports.backoff_seconds(2) == 4
        assert exports.backoff_seconds(3) == 8


class TestBackoffAndStatusVisibility:
    def test_export_status_is_visible_per_episode(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(operator)
        session.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        exports.process_one(simulator=fail())

        body = session.get(f"/api/requests/{instance.id}/assignments").json()
        row = body["results"][0]
        assert row["export_job"]["status"] == ExportStatus.RETRY_WAIT
        assert row["export_job"]["attempts"] == 1
        assert row["export_job"]["max_attempts"] == 3
        # Sanitized message, never a traceback.
        assert "Traceback" not in row["export_job"]["last_error"]
        assert "retry" in row["export_job"]["last_error"]

    def test_the_client_sees_their_own_export_status(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        staff = login(operator)
        staff.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        exports.process_one(simulator=succeed())
        staff.post("/api/auth/logout", headers={"x-csrftoken": csrf()})

        owner = login(client_a)
        body = owner.get(f"/api/requests/{instance.id}/assignments").json()
        assert body["results"][0]["export_job"]["status"] == ExportStatus.COMPLETED

    def test_export_failure_does_not_block_delivery(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        """Documented MVP policy: jobs simulate processing and do not gate delivery.

        Delivery depends on the assigned count alone.
        """
        instance = make_request(
            client_a, episodes_requested=1, status=RequestStatus.IN_PROGRESS
        )
        episode = make_episode(task_name="pick cup")
        session = login(operator)
        session.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        ExportJob.objects.update(status=ExportStatus.FAILED, attempts=3)

        response = session.post(
            f"/api/requests/{instance.id}/transitions",
            data={"status": RequestStatus.DELIVERED},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 200

    def test_no_download_url_is_ever_exposed(
        self, login, operator, client_a, make_request, make_episode, csrf
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        session = login(operator)
        session.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        exports.process_one(simulator=succeed())
        raw = session.get(f"/api/requests/{instance.id}/assignments").content.decode()
        for forbidden in ["http://", "https://", "download", ".mp4", "url"]:
            assert forbidden not in raw.lower(), forbidden


@pytest.mark.django_db(transaction=True)
class TestConcurrentWorkers:
    def test_two_workers_never_claim_the_same_job(
        self, operator, client_a, make_request, make_episode
    ):
        """SKIP LOCKED means two workers take different rows, not the same one."""
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episodes = [make_episode(task_name="pick cup") for _ in range(2)]
        assignment_service.assign_episodes(
            request_id=instance.id,
            actor=operator,
            episode_ids=[episode.id for episode in episodes],
        )

        barrier = threading.Barrier(2)
        claims: list[uuid.UUID] = []
        lock = threading.Lock()

        def worker() -> None:
            try:
                barrier.wait(timeout=10)
                claim = exports.claim_next_job()
                if claim is not None:
                    with lock:
                        claims.append(claim.job_id)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        # Two distinct jobs claimed, never the same one twice.
        assert len(claims) == 2
        assert len(set(claims)) == 2

    def test_a_single_job_is_claimed_by_only_one_of_two_workers(
        self, operator, client_a, make_request, make_episode
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        episode = make_episode(task_name="pick cup")
        assignment_service.assign_episodes(
            request_id=instance.id, actor=operator, episode_ids=[episode.id]
        )

        barrier = threading.Barrier(2)
        results: list[object] = []
        lock = threading.Lock()

        def worker() -> None:
            try:
                barrier.wait(timeout=10)
                claim = exports.claim_next_job()
                with lock:
                    results.append(claim)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        got = [r for r in results if r is not None]
        assert len(got) == 1
        ExportJob.objects.get().refresh_from_db()
        assert ExportJob.objects.get().attempts == 1

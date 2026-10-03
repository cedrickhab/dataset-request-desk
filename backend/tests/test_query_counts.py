"""Query-count guards for the list endpoints.

Each list endpoint must issue a constant number of queries regardless of how
many rows it returns. Without eager loading, the per-row relationships here
(client, episode, export job, assigning user) would each add one query per
row, so these tests fail loudly if a select_related is ever dropped.
"""

from __future__ import annotations

import pytest

from desk.models import RequestStatus
from desk.services import assignments as assignment_service

pytestmark = pytest.mark.django_db


def _count(django_assert_num_queries, expected, fn):
    with django_assert_num_queries(expected):
        fn()


class TestListsDoNotScaleWithRows:
    def test_request_list_is_flat(
        self, login, operator, client_a, client_b, make_request, django_assert_max_num_queries
    ):
        session = login(operator)
        make_request(client_a)
        with django_assert_max_num_queries(8) as one_row:
            session.get("/api/requests")
        baseline = len(one_row)

        for _ in range(10):
            make_request(client_b)
        with django_assert_max_num_queries(baseline) as many_rows:
            session.get("/api/requests")
        # 11 rows must cost no more queries than 1 row.
        assert len(many_rows) <= baseline

    def test_episode_list_is_flat(
        self, login, operator, make_episode, django_assert_max_num_queries
    ):
        session = login(operator)
        make_episode()
        with django_assert_max_num_queries(8) as one_row:
            session.get("/api/episodes")
        baseline = len(one_row)

        for _ in range(20):
            make_episode()
        with django_assert_max_num_queries(baseline) as many_rows:
            session.get("/api/episodes")
        assert len(many_rows) <= baseline

    def test_assignment_list_is_flat(
        self,
        login,
        operator,
        client_a,
        make_request,
        make_episode,
        django_assert_max_num_queries,
    ):
        instance = make_request(client_a, status=RequestStatus.IN_PROGRESS)
        session = login(operator)

        assignment_service.assign_episodes(
            request_id=instance.id,
            actor=operator,
            episode_ids=[make_episode(task_name="pick cup").id],
        )
        with django_assert_max_num_queries(10) as one_row:
            session.get(f"/api/requests/{instance.id}/assignments")
        baseline = len(one_row)

        assignment_service.assign_episodes(
            request_id=instance.id,
            actor=operator,
            episode_ids=[make_episode(task_name="pick cup").id for _ in range(10)],
        )
        with django_assert_max_num_queries(baseline) as many_rows:
            session.get(f"/api/requests/{instance.id}/assignments")
        # Episode, export job and assigning user are all eager-loaded, so 11
        # assignments cost the same as 1.
        assert len(many_rows) <= baseline

    def test_history_is_flat(
        self, login, operator, client_a, make_request, csrf, django_assert_max_num_queries
    ):
        instance = make_request(client_a)
        session = login(operator)
        with django_assert_max_num_queries(8) as one_row:
            session.get(f"/api/requests/{instance.id}/history")
        baseline = len(one_row)

        for target in (RequestStatus.IN_PROGRESS,):
            session.post(
                f"/api/requests/{instance.id}/transitions",
                data={"status": target},
                content_type="application/json",
                headers={"x-csrftoken": csrf()},
            )
        with django_assert_max_num_queries(baseline) as many_rows:
            session.get(f"/api/requests/{instance.id}/history")
        # actor is select_related, so each extra entry adds no query.
        assert len(many_rows) <= baseline

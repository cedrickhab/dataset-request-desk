"""Analytics: exact semantics against a hand-computed fixture."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from desk.models import DatasetRequest, Episode, Quality, RequestStatus
from desk.services import analytics

pytestmark = pytest.mark.django_db


def utc(year, month, day, hour=12, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@pytest.fixture
def fixture_data(db, client_a):
    """A small, fully hand-checkable dataset.

    Episodes (all in August 2026 unless noted):
      01 Aug  arm-01  pick cup     good
      01 Aug  arm-01  pick cup     good     -> 2 good 'pick cup' on day 1
      01 Aug  arm-02  fold towel   bad
      02 Aug  arm-01  pick cup     good     -> 3 good 'pick cup' total
      02 Aug  arm-02  fold towel   good
      02 Aug  arm-02  fold towel   usable
      31 Jul  arm-01  pick cup     good     (before the window)
      01 Sep  arm-01  pick cup     good     (after the window)
    """
    def episode(eid, when, robot, task, quality):
        return Episode.objects.create(
            episode_id=eid,
            robot_id=robot,
            task_name=task,
            recorded_at=when,
            duration_seconds=Decimal("30.00"),
            operator_name="Aline",
            quality=quality,
        )

    episode("E1", utc(2026, 8, 1), "arm-01", "pick cup", Quality.GOOD)
    episode("E2", utc(2026, 8, 1, 23, 59), "arm-01", "pick cup", Quality.GOOD)
    episode("E3", utc(2026, 8, 1), "arm-02", "fold towel", Quality.BAD)
    episode("E4", utc(2026, 8, 2), "arm-01", "pick cup", Quality.GOOD)
    episode("E5", utc(2026, 8, 2), "arm-02", "fold towel", Quality.GOOD)
    episode("E6", utc(2026, 8, 2), "arm-02", "fold towel", Quality.USABLE)
    episode("E7", utc(2026, 7, 31, 23, 59), "arm-01", "pick cup", Quality.GOOD)
    episode("E8", utc(2026, 9, 1, 0, 0), "arm-01", "pick cup", Quality.GOOD)
    return client_a


def make_request_with_times(client, *, created, delivered, status):
    instance = DatasetRequest.objects.create(
        client=client,
        task_name="pick cup",
        episodes_requested=1,
        deadline=date(2099, 1, 1),
        status=status,
    )
    # created_at is auto_now_add, so it needs an explicit UPDATE to backdate.
    DatasetRequest.objects.filter(pk=instance.pk).update(
        created_at=created, first_delivered_at=delivered
    )
    instance.refresh_from_db()
    return instance


class TestWindowBoundaries:
    def test_window_is_half_open_on_the_day_after_end(self):
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 2))
        assert window.lower == utc(2026, 8, 1, 0, 0)
        assert window.upper == utc(2026, 8, 3, 0, 0)

    def test_episodes_exactly_on_the_bounds(self, fixture_data):
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 2))
        rows = analytics.daily_episodes(window)
        total = sum(row["count"] for row in rows)
        # E7 (31 Jul 23:59) and E8 (1 Sep 00:00) are both outside.
        assert total == 6

    def test_single_day_window_includes_that_whole_day(self, fixture_data):
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 1))
        rows = analytics.daily_episodes(window)
        # Includes the 23:59 episode on that day.
        assert sum(row["count"] for row in rows) == 3


class TestDailyEpisodes:
    def test_grouped_by_day_and_robot(self, fixture_data):
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 2))
        rows = analytics.daily_episodes(window)
        assert rows == [
            {"day": "2026-08-01", "robot_id": "arm-01", "count": 2},
            {"day": "2026-08-01", "robot_id": "arm-02", "count": 1},
            {"day": "2026-08-02", "robot_id": "arm-01", "count": 1},
            {"day": "2026-08-02", "robot_id": "arm-02", "count": 2},
        ]

    def test_bad_quality_is_counted_in_daily_totals(self, fixture_data):
        """Daily counts are 'episodes recorded', not 'usable episodes'."""
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 1))
        rows = analytics.daily_episodes(window)
        arm02 = next(r for r in rows if r["robot_id"] == "arm-02")
        assert arm02["count"] == 1


class TestTopGoodTasks:
    def test_counts_only_good_quality(self, fixture_data):
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 2))
        assert analytics.top_good_tasks(window) == [
            {"task_name": "pick cup", "count": 3},
            {"task_name": "fold towel", "count": 1},
        ]

    def test_ties_break_alphabetically(self, db, client_a):
        for index, task in enumerate(["zebra task", "alpha task"]):
            Episode.objects.create(
                episode_id=f"T{index}",
                robot_id="arm-01",
                task_name=task,
                recorded_at=utc(2026, 8, 1),
                duration_seconds=Decimal("10.00"),
                operator_name="Aline",
                quality=Quality.GOOD,
            )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 1))
        # Equal counts, so ordering must be deterministic on task_name.
        assert [row["task_name"] for row in analytics.top_good_tasks(window)] == [
            "alpha task",
            "zebra task",
        ]

    def test_limited_to_five(self, db):
        for index in range(7):
            Episode.objects.create(
                episode_id=f"M{index}",
                robot_id="arm-01",
                task_name=f"task {index}",
                recorded_at=utc(2026, 8, 1),
                duration_seconds=Decimal("10.00"),
                operator_name="Aline",
                quality=Quality.GOOD,
            )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 1))
        assert len(analytics.top_good_tasks(window)) == 5


class TestRequestCounts:
    def test_all_five_statuses_present_including_zeros(self, db, client_a):
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        counts = analytics.request_counts(window)
        assert set(counts) == {
            RequestStatus.SUBMITTED,
            RequestStatus.IN_PROGRESS,
            RequestStatus.DELIVERED,
            RequestStatus.ACCEPTED,
            RequestStatus.REJECTED,
        }
        assert all(value == 0 for value in counts.values())

    def test_grouped_by_current_status_not_status_at_creation(self, db, client_a):
        """A request created in the window counts under where it is NOW."""
        make_request_with_times(
            client_a,
            created=utc(2026, 8, 5),
            delivered=None,
            status=RequestStatus.ACCEPTED,
        )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        counts = analytics.request_counts(window)
        assert counts[RequestStatus.ACCEPTED] == 1
        assert counts[RequestStatus.SUBMITTED] == 0

    def test_requests_created_outside_the_window_are_excluded(self, db, client_a):
        make_request_with_times(
            client_a,
            created=utc(2026, 7, 20),
            delivered=None,
            status=RequestStatus.SUBMITTED,
        )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        assert analytics.request_counts(window)[RequestStatus.SUBMITTED] == 0


class TestMedianDelivery:
    def test_null_when_nothing_was_delivered(self, db, client_a):
        make_request_with_times(
            client_a,
            created=utc(2026, 8, 1),
            delivered=None,
            status=RequestStatus.SUBMITTED,
        )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        # Null, not zero: "no data" and "instant delivery" are different facts.
        assert analytics.median_delivery_seconds(window) is None

    def test_single_request_median_is_its_own_duration(self, db, client_a):
        make_request_with_times(
            client_a,
            created=utc(2026, 8, 1, 0, 0),
            delivered=utc(2026, 8, 1, 2, 0),
            status=RequestStatus.DELIVERED,
        )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        assert analytics.median_delivery_seconds(window) == pytest.approx(7200.0)

    def test_even_count_median_interpolates(self, db, client_a):
        """percentile_cont interpolates, so two values give their mean."""
        make_request_with_times(
            client_a,
            created=utc(2026, 8, 1, 0, 0),
            delivered=utc(2026, 8, 1, 1, 0),
            status=RequestStatus.DELIVERED,
        )
        make_request_with_times(
            client_a,
            created=utc(2026, 8, 2, 0, 0),
            delivered=utc(2026, 8, 2, 3, 0),
            status=RequestStatus.DELIVERED,
        )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        # (3600 + 10800) / 2
        assert analytics.median_delivery_seconds(window) == pytest.approx(7200.0)

    def test_odd_count_median_is_the_middle_value(self, db, client_a):
        for day, hours in [(1, 1), (2, 2), (3, 10)]:
            make_request_with_times(
                client_a,
                created=utc(2026, 8, day, 0, 0),
                delivered=utc(2026, 8, day, hours, 0),
                status=RequestStatus.DELIVERED,
            )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        assert analytics.median_delivery_seconds(window) == pytest.approx(7200.0)

    def test_filtered_by_first_delivery_not_by_creation(self, db, client_a):
        """Created before the window, delivered inside it: counts."""
        make_request_with_times(
            client_a,
            created=utc(2026, 7, 31, 0, 0),
            delivered=utc(2026, 8, 1, 1, 0),
            status=RequestStatus.DELIVERED,
        )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        assert analytics.median_delivery_seconds(window) == pytest.approx(90000.0)

    def test_delivery_outside_the_window_is_excluded(self, db, client_a):
        make_request_with_times(
            client_a,
            created=utc(2026, 8, 1, 0, 0),
            delivered=utc(2026, 9, 5, 0, 0),
            status=RequestStatus.DELIVERED,
        )
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 31))
        assert analytics.median_delivery_seconds(window) is None

    def test_rework_does_not_reset_the_measurement(
        self, login, operator, client_a, make_episode, csrf
    ):
        """first_delivered_at is written once, so rework cannot flatter the metric."""
        instance = make_request_with_times(
            client_a,
            created=utc(2026, 8, 1, 0, 0),
            delivered=utc(2026, 8, 1, 1, 0),
            status=RequestStatus.REJECTED,
        )
        episode = make_episode(task_name="pick cup")
        staff = login(operator)
        staff.post(
            f"/api/requests/{instance.id}/transitions",
            data={"status": RequestStatus.IN_PROGRESS},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        staff.post(
            f"/api/requests/{instance.id}/assignments",
            data={"episode_ids": [str(episode.id)]},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        staff.post(
            f"/api/requests/{instance.id}/transitions",
            data={"status": RequestStatus.DELIVERED},
            content_type="application/json",
            headers={"x-csrftoken": csrf()},
        )
        instance.refresh_from_db()
        assert instance.first_delivered_at == utc(2026, 8, 1, 1, 0)


class TestAnalyticsEndpoint:
    def test_staff_gets_the_full_report_with_semantics(self, login, operator, fixture_data):
        session = login(operator)
        body = session.get("/api/analytics?start=2026-08-01&end=2026-08-02").json()
        assert body["totals"]["episodes_recorded"] == 6
        assert body["totals"]["good_episodes"] == 4
        assert body["top_good_tasks"][0] == {"task_name": "pick cup", "count": 3}
        assert len(body["request_counts"]) == 5
        # Semantics travel with the response so the UI cannot drift from them.
        assert "half-open" in body["semantics"]["window"]

    def test_client_is_forbidden(self, login, client_a, fixture_data):
        session = login(client_a)
        assert session.get("/api/analytics?start=2026-08-01&end=2026-08-02").status_code == 403

    def test_start_after_end_is_400(self, login, operator):
        session = login(operator)
        response = session.get("/api/analytics?start=2026-09-01&end=2026-08-01")
        assert response.status_code == 400
        assert "start" in response.json()["error"]["fields"]

    def test_range_over_the_limit_is_400(self, login, operator):
        session = login(operator)
        response = session.get("/api/analytics?start=2024-01-01&end=2026-12-31")
        assert response.status_code == 400

    def test_missing_dates_are_400(self, login, operator):
        session = login(operator)
        assert session.get("/api/analytics").status_code == 400

    def test_malformed_date_is_400(self, login, operator):
        session = login(operator)
        assert session.get("/api/analytics?start=soon&end=later").status_code == 400

    def test_exactly_the_maximum_range_is_accepted(self, login, operator, settings):
        session = login(operator)
        start = date(2026, 1, 1)
        end = start + timedelta(days=settings.ANALYTICS_MAX_RANGE_DAYS - 1)
        response = session.get(f"/api/analytics?start={start}&end={end}")
        assert response.status_code == 200

    def test_analytics_does_not_leak_cross_client_identifiers(
        self, login, operator, client_a, client_b
    ):
        """Aggregates only: no client names or request ids in the response."""
        make_request_with_times(
            client_b,
            created=utc(2026, 8, 5),
            delivered=None,
            status=RequestStatus.SUBMITTED,
        )
        session = login(operator)
        raw = session.get("/api/analytics?start=2026-08-01&end=2026-08-31").content.decode()
        assert client_b.name not in raw
        assert str(client_b.id) not in raw


class TestQueryEfficiency:
    def test_report_runs_a_bounded_number_of_queries(
        self, fixture_data, django_assert_max_num_queries
    ):
        """Aggregation happens in the database.

        The guard is the point: if someone replaced a GROUP BY with a Python
        loop over rows, the query count would scale with the data and this
        would fail.
        """
        window = analytics.Window(start=date(2026, 8, 1), end=date(2026, 8, 2))
        with django_assert_max_num_queries(6):
            analytics.build_report(window)

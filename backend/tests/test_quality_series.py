"""Episode-quality-over-time series (dashboard chart aggregation).

The chart plots episodes successfully imported per day, grouped by quality.
These tests pin the semantics that matter to it: the import timestamp (never
the recording date), Africa/Kigali day boundaries, zero-filling that
distinguishes confirmed zeros from unavailable history, duplicate imports
counted once, and the staff-only surface.
"""

from __future__ import annotations

import io
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings

from desk.models import Episode, Quality
from desk.services import analytics, csv_import

pytestmark = pytest.mark.django_db

SEED_CSV = Path(settings.REPO_ROOT) / "seed" / "episodes.csv"


def import_at(
    episode_id: str,
    when: datetime,
    quality: str = Quality.GOOD,
    recorded_at: datetime | None = None,
) -> Episode:
    """Create an episode and pin its persisted import timestamp.

    imported_at is auto_now_add, exactly as in production; the explicit UPDATE
    is the same backdating a late-arriving row would need in a test.
    """
    episode = Episode.objects.create(
        episode_id=episode_id,
        robot_id="arm-01",
        task_name="pick cup",
        recorded_at=recorded_at or when,
        duration_seconds=Decimal("30.00"),
        operator_name="Aline",
        quality=quality,
    )
    Episode.objects.filter(pk=episode.pk).update(imported_at=when)
    episode.refresh_from_db()
    return episode


def window(start: str, end: str) -> analytics.Window:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return analytics.Window(start=start_date, end=end_date)


def counts_by_date(window_: analytics.Window) -> dict[str, dict[str, int]]:
    series = analytics.quality_series(window_)
    return {day["date"]: day for day in series["days"]}


class TestDailyQualityAggregation:
    def test_counts_by_day_and_quality(self):
        import_at("E1", datetime(2026, 10, 1, 10, 0, tzinfo=UTC), Quality.GOOD)
        import_at("E2", datetime(2026, 10, 1, 18, 0, tzinfo=UTC), Quality.GOOD)
        import_at("E3", datetime(2026, 10, 1, 9, 0, tzinfo=UTC), Quality.USABLE)
        import_at("E4", datetime(2026, 10, 2, 12, 0, tzinfo=UTC), Quality.BAD)
        import_at("E5", datetime(2026, 10, 2, 12, 0, tzinfo=UTC), Quality.BAD)

        days = counts_by_date(window("2026-10-01", "2026-10-02"))
        assert days["2026-10-01"] == {"date": "2026-10-01", "good": 2, "usable": 1, "bad": 0}
        assert days["2026-10-02"] == {"date": "2026-10-02", "good": 0, "usable": 0, "bad": 2}

    def test_uses_import_timestamp_not_recording_date(self):
        """A clip recorded in August but imported in October counts in October."""
        import_at(
            "E1",
            datetime(2026, 10, 3, 8, 0, tzinfo=UTC),
            recorded_at=datetime(2026, 8, 1, 8, 0, tzinfo=UTC),
        )

        october = counts_by_date(window("2026-10-01", "2026-10-31"))
        assert october["2026-10-03"]["good"] == 1
        august = counts_by_date(window("2026-08-01", "2026-08-31"))
        assert august == {}

    def test_kigali_day_boundary(self):
        """23:30 UTC on the 2nd is already 01:30 on the 3rd in Kigali (UTC+2)."""
        import_at("E1", datetime(2026, 10, 2, 23, 30, tzinfo=UTC))

        days = counts_by_date(window("2026-10-01", "2026-10-05"))
        assert "2026-10-03" in days
        assert days["2026-10-03"]["good"] == 1
        assert "2026-10-02" not in days  # before the first persisted import

    def test_boundary_excludes_the_next_kigali_day(self):
        """22:00 UTC on the 2nd is 00:00 on the 3rd in Kigali; 21:59 is day 2."""
        import_at("E1", datetime(2026, 10, 2, 21, 59, tzinfo=UTC))
        import_at("E2", datetime(2026, 10, 2, 22, 0, tzinfo=UTC))

        days = counts_by_date(window("2026-10-01", "2026-10-05"))
        assert days["2026-10-02"]["good"] == 1
        assert days["2026-10-03"]["good"] == 1

    def test_duplicate_imports_are_counted_once(self):
        """The create-only importer means a re-run cannot double any count."""
        first = csv_import.import_from_path(str(SEED_CSV))
        second = csv_import.import_from_path(str(SEED_CSV))
        assert first.imported == 172
        assert second.imported == 0
        assert Episode.objects.count() == 172
        Episode.objects.update(imported_at=datetime(2026, 10, 4, 12, tzinfo=UTC))

        series = analytics.quality_series(window("2026-01-01", "2026-12-31"))
        assert series["total_imported"] == 172

    def test_window_is_half_open_in_the_business_zone(self):
        import_at("E1", datetime(2026, 10, 4, 21, 59, tzinfo=UTC))  # 23:59 Kigali, day 4
        import_at("E2", datetime(2026, 10, 4, 22, 0, tzinfo=UTC))  # 00:00 Kigali, day 5

        days = counts_by_date(window("2026-10-04", "2026-10-04"))
        assert days["2026-10-04"]["good"] == 1  # the 21:59 import only

    def test_all_zeroes_inside_reported_history(self):
        """Confirmed zero: an empty day after imports began is zero, not absent."""
        import_at("E1", datetime(2026, 10, 1, 8, 0, tzinfo=UTC))
        import_at("E2", datetime(2026, 10, 3, 8, 0, tzinfo=UTC))

        series = analytics.quality_series(window("2026-10-01", "2026-10-05"))
        assert [day["date"] for day in series["days"]] == [
            "2026-10-01",
            "2026-10-02",
            "2026-10-03",
            "2026-10-04",
            "2026-10-05",
        ]
        assert series["days"][1]["good"] == 0
        assert series["total_imported"] == 2

    def test_history_before_the_first_import_is_unavailable(self):
        """Nothing was ever imported in September: no rows, not zeros."""
        import_at("E1", datetime(2026, 10, 2, 8, 0, tzinfo=UTC))

        series = analytics.quality_series(window("2026-09-01", "2026-09-30"))
        assert series["days"] == []
        assert series["total_imported"] == 0

    def test_single_date_with_data_gives_one_honest_point(self):
        import_at("E1", datetime(2026, 10, 2, 8, 0, tzinfo=UTC), Quality.USABLE)

        series = analytics.quality_series(window("2026-10-01", "2026-10-02"))
        assert len(series["days"]) == 1
        assert series["data_start"] == "2026-10-02"
        assert series["days"][0] == {
            "date": "2026-10-02",
            "good": 0,
            "usable": 1,
            "bad": 0,
        }

    def test_no_data_at_all_reports_null_start_and_empty_series(self):
        series = analytics.quality_series(window("2026-10-01", "2026-10-07"))
        assert series["days"] == []
        assert series["data_start"] is None
        assert series["total_imported"] == 0

    def test_data_start_is_the_earliest_import_even_outside_the_window(self):
        import_at("E1", datetime(2026, 6, 15, 8, 0, tzinfo=UTC))

        series = analytics.quality_series(window("2026-10-01", "2026-10-07"))
        assert series["data_start"] == "2026-06-15"
        assert series["days"] == [
            {"date": f"2026-10-{day:02d}", "good": 0, "usable": 0, "bad": 0}
            for day in range(1, 8)
        ]

    def test_response_shape_and_semantics(self):
        import_at("E1", datetime(2026, 10, 2, 8, 0, tzinfo=UTC))
        series = analytics.quality_series(window("2026-10-01", "2026-10-03"))
        assert series["timezone"] == "Africa/Kigali"
        assert series["start"] == "2026-10-01"
        assert series["end"] == "2026-10-03"
        assert set(series["days"][0]) == {"date", "good", "usable", "bad"}
        assert "business time zone" in series["semantics"]["dates"]
        assert "imported_at" in series["semantics"]["bucket"]


class TestQualitySeriesEndpoint:
    def test_operator_gets_the_series(self, login, operator):
        import_at("E1", datetime(2026, 10, 2, 8, 0, tzinfo=UTC))
        session = login(operator)
        response = session.get("/api/analytics/episode-quality?start=2026-10-01&end=2026-10-03")
        assert response.status_code == 200
        body = response.json()
        assert body["timezone"] == "Africa/Kigali"
        assert body["total_imported"] == 1
        assert body["days"][0]["date"] == "2026-10-02"

    def test_client_is_forbidden(self, login, client_a):
        session = login(client_a)
        response = session.get("/api/analytics/episode-quality?start=2026-10-01&end=2026-10-03")
        assert response.status_code == 403

    def test_operator_and_admin_both_allowed(self, login, operator, admin):
        assert (
            login(operator).get(
                "/api/analytics/episode-quality?start=2026-10-01&end=2026-10-03"
            ).status_code
            == 200
        )
        assert (
            login(admin).get(
                "/api/analytics/episode-quality?start=2026-10-01&end=2026-10-03"
            ).status_code
            == 200
        )

    def test_anonymous_is_unauthenticated(self, api):
        response = api.get("/api/analytics/episode-quality?start=2026-10-01&end=2026-10-03")
        assert response.status_code == 401

    def test_invalid_range_is_400(self, login, operator):
        session = login(operator)
        assert (
            session.get("/api/analytics/episode-quality?start=2026-10-03&end=2026-10-01")
        ).status_code == 400
        assert (session.get("/api/analytics/episode-quality")).status_code == 400

    def test_range_over_the_limit_is_400(self, login, operator):
        session = login(operator)
        response = session.get(
            "/api/analytics/episode-quality?start=2024-01-01&end=2026-12-31"
        )
        assert response.status_code == 400

    def test_aggregation_runs_a_bounded_number_of_queries(
        self, django_assert_max_num_queries
    ):
        import_at("E1", datetime(2026, 10, 2, 8, 0, tzinfo=UTC))
        with django_assert_max_num_queries(4):
            analytics.quality_series(window("2026-10-01", "2026-10-31"))


class TestImporterAgreement:
    def test_invalid_rows_never_reach_the_counts(self):
        """Rejected CSV rows are not successful imports and count for nothing."""
        header = (
            "episode_id,robot_id,task_name,recorded_at,"
            "duration_seconds,operator_name,quality"
        )
        rows = "\n".join(
            [
                header,
                "EP-00001,arm-01,pick cup,2026-10-02T10:00:00,30,Aline,good",
                "EP-00002,arm-01,pick cup,2026-10-02T10:00:00,-5,Aline,good",
                "EP-00002,arm-01,pick cup,2026-10-02T10:00:00,30,Aline,good",
                "EP-00001,arm-01,pick cup,2026-10-02T10:00:00,30,Aline,good",
                "EP-00001,arm-01,pick cup,2026-10-02T10:00:00,35,Aline,good",
                "EP-00003,arm-01,pick cup,2026-10-02T10:00:00,30,Aline,excellent",
            ]
        )
        summary = csv_import.import_episodes(io.StringIO(rows + "\n"))
        assert summary.imported == 2  # a valid row after an invalid row still imports
        assert summary.invalid == 2
        assert summary.duplicate == 1
        assert summary.conflict == 1
        assert summary.processed == summary.imported + summary.skipped
        Episode.objects.update(imported_at=datetime(2026, 10, 4, 12, tzinfo=UTC))

        series = analytics.quality_series(window("2026-10-01", "2026-10-31"))
        assert series["total_imported"] == 2
        assert series["days"][0]["good"] == 2

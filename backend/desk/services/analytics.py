"""Analytics aggregated in PostgreSQL.

Every figure here is produced by a GROUP BY or an aggregate executed in the
database. No query returns raw episode or request rows to Python, so response
size and memory stay flat as the tables grow.

Date semantics (also returned to the caller in `semantics`, so the UI cannot
drift from them):
  * start and end are inclusive calendar dates, read as UTC
  * the half-open window is [start 00:00, (end + 1 day) 00:00)
  * episode metrics filter recorded_at
  * request counts cover requests CREATED in the window, grouped by their
    CURRENT status
  * the median covers requests FIRST delivered in the window, measuring
    created_at -> first_delivered_at; later rework does not reset it
  * no deliveries in the window yields null, not zero
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from django.db import connection
from django.db.models import Count, Q
from django.db.models.functions import TruncDay

from desk.models import DatasetRequest, Episode, Quality, RequestStatus


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    @property
    def lower(self) -> datetime:
        return datetime.combine(self.start, time.min, tzinfo=UTC)

    @property
    def upper(self) -> datetime:
        """Exclusive upper bound: midnight after the inclusive end date."""
        return datetime.combine(
            self.end + timedelta(days=1), time.min, tzinfo=UTC
        )


SEMANTICS = {
    "dates": "start and end are inclusive calendar dates interpreted as UTC",
    "window": "half-open [start 00:00 UTC, end+1 day 00:00 UTC)",
    "daily_episodes": "episodes grouped by recorded_at day and robot_id",
    "request_counts": (
        "requests created within the window, grouped by their current status; "
        "all five statuses are always present"
    ),
    "median_delivery_seconds": (
        "requests first delivered within the window, measured created_at to "
        "first_delivered_at; null when there were none"
    ),
    "top_good_tasks": (
        "top 5 task names by count of good-quality episodes recorded in the "
        "window, ordered by count desc then task_name asc"
    ),
}


def daily_episodes(window: Window) -> list[dict[str, object]]:
    """Per-day, per-robot episode counts. GROUP BY in the database."""
    rows = (
        Episode.objects.filter(
            recorded_at__gte=window.lower, recorded_at__lt=window.upper
        )
        .annotate(day=TruncDay("recorded_at"))
        .values("day", "robot_id")
        .annotate(count=Count("id"))
        .order_by("day", "robot_id")
    )
    return [
        {
            "day": row["day"].date().isoformat(),
            "robot_id": row["robot_id"],
            "count": row["count"],
        }
        for row in rows
    ]


def request_counts(window: Window) -> dict[str, int]:
    """Counts by current status for requests created in the window."""
    rows = (
        DatasetRequest.objects.filter(
            created_at__gte=window.lower, created_at__lt=window.upper
        )
        .values("status")
        .annotate(count=Count("id"))
    )
    # Seed every status so the caller always gets five keys, zeros included.
    counts = {choice.value: 0 for choice in RequestStatus}
    for row in rows:
        counts[row["status"]] = row["count"]
    return counts


def median_delivery_seconds(window: Window) -> float | None:
    """Median first-delivery turnaround, via percentile_cont in PostgreSQL.

    percentile_cont is an ordered-set aggregate with no ORM equivalent, so this
    is raw SQL — parameterized, never string-interpolated.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT percentile_cont(0.5) WITHIN GROUP (
                       ORDER BY EXTRACT(EPOCH FROM (first_delivered_at - created_at))
                   )
            FROM desk_datasetrequest
            WHERE first_delivered_at >= %s AND first_delivered_at < %s
            """,
            [window.lower, window.upper],
        )
        row = cursor.fetchone()
    # NULL when no rows matched, which is the "no deliveries" case.
    if row is None or row[0] is None:
        return None
    return float(row[0])


def top_good_tasks(window: Window, limit: int = 5) -> list[dict[str, object]]:
    """Top task names by good-episode count."""
    rows = (
        Episode.objects.filter(
            recorded_at__gte=window.lower,
            recorded_at__lt=window.upper,
            quality=Quality.GOOD,
        )
        .values("task_name")
        .annotate(count=Count("id"))
        # Tie-break on task_name so the ordering is deterministic across runs.
        .order_by("-count", "task_name")[:limit]
    )
    return [{"task_name": row["task_name"], "count": row["count"]} for row in rows]


def summary_totals(window: Window) -> dict[str, int]:
    """Headline counts for the metric cards, as one aggregate query each."""
    episode_totals = Episode.objects.filter(
        recorded_at__gte=window.lower, recorded_at__lt=window.upper
    ).aggregate(
        episodes=Count("id"),
        good_episodes=Count("id", filter=Q(quality=Quality.GOOD)),
    )
    requests_created = DatasetRequest.objects.filter(
        created_at__gte=window.lower, created_at__lt=window.upper
    ).count()
    return {
        "episodes_recorded": episode_totals["episodes"],
        "good_episodes": episode_totals["good_episodes"],
        "requests_created": requests_created,
    }


def build_report(window: Window) -> dict[str, object]:
    totals = summary_totals(window)
    return {
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "totals": totals,
        "daily_episodes": daily_episodes(window),
        "request_counts": request_counts(window),
        "median_delivery_seconds": median_delivery_seconds(window),
        "top_good_tasks": top_good_tasks(window),
        "semantics": SEMANTICS,
    }

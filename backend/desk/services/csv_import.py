"""Episode CSV import, shared by the API endpoint and the CLI command.

Create-only by policy: an existing episode_id is never overwritten. That makes
re-running the same file a no-op after the first pass, which is the idempotency
the brief asks for, and it means a later corrupted export cannot silently
rewrite good history.

Row outcomes:
  imported   - new episode stored
  duplicate  - episode_id exists and the payload matches what is stored
  conflict   - episode_id exists and the payload differs (never overwritten)
  invalid    - failed validation; reason reported per row
  blank      - row parsed to nothing but whitespace
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import IO

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from desk.models import Episode, Quality
from desk.normalize import (
    normalize_episode_id,
    normalize_operator_name,
    normalize_quality,
    normalize_robot_id,
    normalize_task_name,
)

REQUIRED_HEADERS = [
    "episode_id",
    "robot_id",
    "task_name",
    "recorded_at",
    "duration_seconds",
    "operator_name",
    "quality",
]


class ImportAborted(Exception):
    """The file itself is unusable; no rows were considered."""


@dataclass
class RowIssue:
    line: int
    episode_id: str
    code: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "line": self.line,
            "episode_id": self.episode_id,
            "code": self.code,
            "reason": self.reason,
        }


@dataclass
class ImportSummary:
    """Row tallies.

    Invariants, asserted by the tests:
        processed == imported + skipped
        skipped   == duplicate + conflict + invalid
    `processed` counts data rows only: the header and whitespace-only rows are
    excluded, and blank rows are reported separately as skipped_blank.
    """

    processed: int = 0
    imported: int = 0
    skipped: int = 0
    duplicate: int = 0
    conflict: int = 0
    invalid: int = 0
    skipped_blank: int = 0
    issues: list[RowIssue] = field(default_factory=list)
    issues_truncated: bool = False
    max_reported_issues: int = settings.IMPORT_MAX_REPORTED_ISSUES

    def add_issue(self, issue: RowIssue) -> None:
        """Counts always reflect every row; the detail list is capped."""
        if len(self.issues) < self.max_reported_issues:
            self.issues.append(issue)
        else:
            self.issues_truncated = True

    def as_dict(self) -> dict[str, object]:
        return {
            "processed": self.processed,
            "imported": self.imported,
            "skipped": self.skipped,
            "duplicate": self.duplicate,
            "conflict": self.conflict,
            "invalid": self.invalid,
            "skipped_blank": self.skipped_blank,
            "issues": [issue.as_dict() for issue in self.issues],
            "issues_truncated": self.issues_truncated,
        }


# --- field parsing ------------------------------------------------------------

_DATE_FORMATS = (
    # ISO with explicit zone, ISO naive, space separator, and day-first.
    ("%Y-%m-%dT%H:%M:%S%z", True),
    ("%Y-%m-%dT%H:%M:%S", False),
    ("%Y-%m-%d %H:%M:%S", False),
    ("%d/%m/%Y %H:%M", False),
)


def parse_recorded_at(raw: str) -> datetime:
    """Parse a timestamp, rejecting date-only and impossible values.

    A naive value is interpreted as UTC. strptime does the calendar validation
    for us, so 2026-02-31 is rejected rather than rolled over.
    """
    value = (raw or "").strip()
    if not value:
        raise ValueError("recorded_at is required")

    normalized = value.replace("Z", "+0000") if value.endswith("Z") else value
    for fmt, aware in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        if not aware:
            parsed = parsed.replace(tzinfo=UTC)
        parsed = parsed.astimezone(UTC)
        if parsed > timezone.now():
            raise ValueError("recorded_at is in the future")
        return parsed
    raise ValueError("recorded_at is not a recognised timestamp")


def parse_duration(raw: str) -> Decimal:
    value = (raw or "").strip()
    if not value:
        raise ValueError("duration_seconds is required")
    try:
        duration = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("duration_seconds is not a number") from exc
    # Decimal accepts 'NaN' and 'Infinity' as literals; both would pass a
    # naive > 0 test and corrupt every later aggregate.
    if not duration.is_finite():
        raise ValueError("duration_seconds must be a finite number")
    if duration <= 0:
        raise ValueError("duration_seconds must be greater than zero")
    if duration > settings.EPISODE_MAX_DURATION_SECONDS:
        raise ValueError(
            f"duration_seconds exceeds the {settings.EPISODE_MAX_DURATION_SECONDS}s limit"
        )
    return duration.quantize(Decimal("0.01"))


def parse_quality(raw: str) -> str:
    value = normalize_quality(raw)
    if not value:
        raise ValueError("quality is required")
    if value not in {choice.value for choice in Quality}:
        raise ValueError(f"quality '{value}' is not good, usable or bad")
    return value


@dataclass(frozen=True)
class ParsedRow:
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: Decimal
    operator_name: str
    quality: str


def parse_row(values: dict[str, str]) -> ParsedRow:
    """Normalize and validate one row, or raise ValueError with the reason."""
    episode_id = normalize_episode_id(values.get("episode_id"))
    if not episode_id:
        raise ValueError("episode_id is required")

    robot_id = normalize_robot_id(values.get("robot_id"))
    if not robot_id:
        raise ValueError("robot_id is required")
    if robot_id not in set(settings.KNOWN_ROBOT_IDS):
        raise ValueError(f"robot_id '{robot_id}' is not a known robot")

    task_name = normalize_task_name(values.get("task_name"))
    if not task_name:
        raise ValueError("task_name is required")
    if len(task_name) > 120:
        raise ValueError("task_name exceeds 120 characters")

    operator_name = normalize_operator_name(values.get("operator_name"))
    if not operator_name:
        # The brief lists operator_name as a field; a recording with no known
        # recordist is not traceable, so it is rejected rather than defaulted.
        raise ValueError("operator_name is required")

    return ParsedRow(
        episode_id=episode_id,
        robot_id=robot_id,
        task_name=task_name,
        recorded_at=parse_recorded_at(values.get("recorded_at", "")),
        duration_seconds=parse_duration(values.get("duration_seconds", "")),
        operator_name=operator_name,
        quality=parse_quality(values.get("quality", "")),
    )


def _matches_stored(row: ParsedRow, stored: Episode) -> bool:
    """True when a repeat row carries the same content as the stored episode."""
    return (
        stored.robot_id == row.robot_id
        and stored.task_name == row.task_name
        and stored.recorded_at == row.recorded_at
        and stored.duration_seconds == row.duration_seconds
        and stored.operator_name == row.operator_name
        and stored.quality == row.quality
    )


# --- file handling ------------------------------------------------------------


def _read_header(reader: csv.reader) -> list[str]:  # type: ignore[valid-type]
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ImportAborted("The file is empty.") from exc
    # Strip a UTF-8 BOM from the first cell if the file was exported from Excel.
    if header and header[0].startswith("﻿"):
        header[0] = header[0][1:]
    cleaned = [cell.strip().lower() for cell in header]
    if cleaned[: len(REQUIRED_HEADERS)] != REQUIRED_HEADERS:
        raise ImportAborted(
            "The header row must be exactly: " + ", ".join(REQUIRED_HEADERS)
        )
    return cleaned


def iter_rows(stream: IO[str]) -> Iterator[tuple[int, list[str]]]:
    """Yield (physical line number, cells) for each data row.

    csv.reader handles quoted commas and embedded newlines; the file is never
    split on ',' by hand and never read into memory whole.
    """
    reader = csv.reader(stream)
    _read_header(reader)
    for cells in reader:
        yield reader.line_num, cells


def import_episodes(
    stream: IO[str], *, max_rows: int | None = None, max_issues: int | None = None
) -> ImportSummary:
    """Import from an already-opened text stream."""
    limit = settings.IMPORT_MAX_ROWS if max_rows is None else max_rows
    summary = ImportSummary(
        max_reported_issues=(
            settings.IMPORT_MAX_REPORTED_ISSUES if max_issues is None else max_issues
        )
    )

    for line, cells in iter_rows(stream):
        # A row that is entirely whitespace is counted but not treated as an
        # error. csv.reader already drops truly empty physical lines, so this
        # count is "whitespace-only parsed rows", not "blank lines in the file".
        if not any(cell.strip() for cell in cells):
            # Counted on its own, and deliberately NOT in `processed` or
            # `skipped`, so the invariant below always holds:
            #   processed == imported + skipped
            #   skipped   == duplicate + conflict + invalid
            summary.skipped_blank += 1
            continue

        summary.processed += 1
        if summary.processed > limit:
            raise ImportAborted(
                f"The file exceeds the {limit} row limit. Split it and import again."
            )

        if len(cells) != len(REQUIRED_HEADERS):
            summary.invalid += 1
            summary.skipped += 1
            summary.add_issue(
                RowIssue(
                    line=line,
                    episode_id=normalize_episode_id(cells[0] if cells else ""),
                    code="malformed_row",
                    reason=(
                        f"expected {len(REQUIRED_HEADERS)} columns, found {len(cells)}"
                    ),
                )
            )
            continue

        # strict=True is safe: the column count was checked immediately above.
        # If that check is ever removed, this raises instead of silently
        # dropping or mis-aligning a column.
        values = dict(zip(REQUIRED_HEADERS, cells, strict=True))
        try:
            row = parse_row(values)
        except ValueError as exc:
            summary.invalid += 1
            summary.skipped += 1
            summary.add_issue(
                RowIssue(
                    line=line,
                    episode_id=normalize_episode_id(values.get("episode_id")),
                    code="invalid",
                    reason=str(exc),
                )
            )
            continue

        _store_row(row, line, summary)

    return summary


def _store_row(row: ParsedRow, line: int, summary: ImportSummary) -> None:
    """Insert one row in its own savepoint.

    Per-row atomicity is the point: one bad row must not roll back the valid
    rows that came before it, and an IntegrityError leaves the surrounding
    transaction unusable until the savepoint is released.
    """
    try:
        with transaction.atomic():
            Episode.objects.create(
                episode_id=row.episode_id,
                robot_id=row.robot_id,
                task_name=row.task_name,
                recorded_at=row.recorded_at,
                duration_seconds=row.duration_seconds,
                operator_name=row.operator_name,
                quality=row.quality,
            )
    except IntegrityError:
        # Either the id was already in the file above us, or a concurrent
        # import committed it first. Classify only now that the savepoint has
        # rolled back and the connection is usable again.
        stored = Episode.objects.filter(episode_id=row.episode_id).first()
        if stored is None:
            summary.invalid += 1
            summary.skipped += 1
            summary.add_issue(
                RowIssue(
                    line=line,
                    episode_id=row.episode_id,
                    code="rejected",
                    reason="the database rejected this row",
                )
            )
            return
        if _matches_stored(row, stored):
            summary.duplicate += 1
            summary.skipped += 1
            summary.add_issue(
                RowIssue(
                    line=line,
                    episode_id=row.episode_id,
                    code="duplicate",
                    reason="already imported with identical values",
                )
            )
        else:
            summary.conflict += 1
            summary.skipped += 1
            summary.add_issue(
                RowIssue(
                    line=line,
                    episode_id=row.episode_id,
                    code="conflict",
                    reason="already imported with different values; left unchanged",
                )
            )
        return
    summary.imported += 1


def import_from_path(path: str, **kwargs: object) -> ImportSummary:
    # newline="" is required by the csv module so quoted embedded newlines
    # survive; utf-8-sig transparently drops a BOM.
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return import_episodes(handle, **kwargs)  # type: ignore[arg-type]


def iter_issue_lines(issues: Iterable[RowIssue]) -> Iterator[str]:
    import json

    for issue in issues:
        yield json.dumps(issue.as_dict())

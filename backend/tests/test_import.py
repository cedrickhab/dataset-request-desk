"""CSV import: idempotency, normalization and row-level reporting."""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from desk.models import Episode
from desk.services import csv_import

pytestmark = pytest.mark.django_db

HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality"
SEED_CSV = Path(settings.REPO_ROOT) / "seed" / "episodes.csv"


def run(text: str) -> csv_import.ImportSummary:
    return csv_import.import_episodes(io.StringIO(text))


def row(
    episode_id="EP-00001",
    robot="arm-01",
    task="pick cup",
    recorded="2026-08-01T10:00:00",
    duration="30",
    operator="Aline",
    quality="good",
) -> str:
    return f"{episode_id},{robot},{task},{recorded},{duration},{operator},{quality}"


class TestHeaderHandling:
    def test_missing_header_aborts(self):
        with pytest.raises(csv_import.ImportAborted):
            run("a,b,c\n1,2,3\n")

    def test_empty_file_aborts(self):
        with pytest.raises(csv_import.ImportAborted):
            run("")

    def test_utf8_bom_is_tolerated(self):
        summary = run("﻿" + HEADER + "\n" + row() + "\n")
        assert summary.imported == 1

    def test_header_case_and_padding_are_tolerated(self):
        padded = "Episode_ID, robot_id ,TASK_NAME,recorded_at,duration_seconds,operator_name,quality"
        summary = run(padded + "\n" + row() + "\n")
        assert summary.imported == 1


class TestNormalization:
    def test_episode_id_is_uppercased(self):
        run(HEADER + "\n" + row(episode_id="ep-00123") + "\n")
        assert Episode.objects.get().episode_id == "EP-00123"

    def test_task_and_robot_are_lowercased_and_collapsed(self):
        run(HEADER + "\n" + row(task="  Pick   Cup ", robot=" ARM-01 ") + "\n")
        stored = Episode.objects.get()
        assert stored.task_name == "pick cup"
        assert stored.robot_id == "arm-01"

    def test_quality_casing_is_normalized(self):
        summary = run(HEADER + "\n" + row(quality="GOOD") + "\n")
        assert summary.imported == 1
        assert Episode.objects.get().quality == "good"

    def test_quoted_comma_in_task_name_is_preserved(self):
        line = 'EP-00500,arm-03,"pick cup, then place",2026-08-21T11:00:00,40,Eric,good'
        summary = run(HEADER + "\n" + line + "\n")
        assert summary.imported == 1
        # Parsed by the csv module, not split on ','.
        assert Episode.objects.get().task_name == "pick cup, then place"

    @pytest.mark.parametrize(
        "raw,expected_iso",
        [
            ("2026-08-14T09:20:00Z", "2026-08-14T09:20:00+00:00"),
            ("2026-08-14 09:12:00", "2026-08-14T09:12:00+00:00"),
            ("14/08/2026 09:15", "2026-08-14T09:15:00+00:00"),
            ("2026-08-14T09:15:00", "2026-08-14T09:15:00+00:00"),
        ],
    )
    def test_accepted_timestamp_formats(self, raw, expected_iso):
        summary = run(HEADER + "\n" + row(recorded=raw) + "\n")
        assert summary.imported == 1, summary.issues
        assert Episode.objects.get().recorded_at.isoformat() == expected_iso

    def test_decimal_duration_is_kept(self):
        run(HEADER + "\n" + row(duration="45.5") + "\n")
        assert Episode.objects.get().duration_seconds == Decimal("45.50")


class TestValidation:
    @pytest.mark.parametrize(
        "kwargs,fragment",
        [
            ({"episode_id": ""}, "episode_id is required"),
            ({"robot": ""}, "robot_id is required"),
            ({"robot": "arm-99"}, "not a known robot"),
            ({"task": ""}, "task_name is required"),
            ({"operator": ""}, "operator_name is required"),
            ({"quality": ""}, "quality is required"),
            ({"quality": "excellent"}, "not good, usable or bad"),
            ({"duration": ""}, "duration_seconds is required"),
            ({"duration": "N/A"}, "not a number"),
            ({"duration": "-5"}, "greater than zero"),
            ({"duration": "0"}, "greater than zero"),
            ({"duration": "999999"}, "exceeds"),
            ({"recorded": "not a date"}, "not a recognised timestamp"),
            ({"recorded": "2031-01-01T00:00:00"}, "in the future"),
            ({"recorded": "2026-08-14"}, "not a recognised timestamp"),
        ],
    )
    def test_invalid_rows_are_skipped_with_a_reason(self, kwargs, fragment):
        summary = run(HEADER + "\n" + row(**kwargs) + "\n")
        assert summary.imported == 0
        assert summary.invalid == 1
        assert fragment in summary.issues[0].reason
        assert Episode.objects.count() == 0

    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
    def test_non_finite_durations_are_rejected(self, literal):
        """Decimal() accepts these literals; a naive > 0 check would let them in."""
        summary = run(HEADER + "\n" + row(duration=literal) + "\n")
        assert summary.imported == 0
        assert "finite" in summary.issues[0].reason

    def test_date_only_timestamp_is_not_silently_accepted(self):
        summary = run(HEADER + "\n" + row(recorded="2026-08-14") + "\n")
        assert summary.invalid == 1

    def test_impossible_calendar_date_is_rejected(self):
        summary = run(HEADER + "\n" + row(recorded="2026-02-31T10:00:00") + "\n")
        assert summary.invalid == 1

    def test_short_row_is_reported_as_malformed(self):
        summary = run(HEADER + "\nEP-90001,arm-02,open drawer,2026-08-20T10:00:00,30\n")
        assert summary.invalid == 1
        assert summary.issues[0].code == "malformed_row"
        assert "found 5" in summary.issues[0].reason

    def test_bad_quality_episodes_are_stored(self):
        """'bad' is a valid rating, not an invalid row. It simply cannot be assigned."""
        summary = run(HEADER + "\n" + row(quality="bad") + "\n")
        assert summary.imported == 1
        assert Episode.objects.get().quality == "bad"

    def test_blank_rows_are_counted_separately(self):
        summary = run(HEADER + "\n" + row() + "\n   ,,,,,,\n")
        assert summary.imported == 1
        assert summary.skipped_blank == 1
        # Blank rows are outside processed, keeping the invariant clean.
        assert summary.processed == 1

    def test_one_bad_row_does_not_discard_the_good_rows(self):
        """Per-row savepoints: the classic 'whole file rolled back' bug."""
        text = "\n".join(
            [
                HEADER,
                row(episode_id="EP-00001"),
                row(episode_id="EP-00002", duration="-5"),
                row(episode_id="EP-00003"),
                "",
            ]
        )
        summary = run(text)
        assert summary.imported == 2
        assert summary.invalid == 1
        assert set(Episode.objects.values_list("episode_id", flat=True)) == {
            "EP-00001",
            "EP-00003",
        }


class TestIdempotencyAndConflicts:
    def test_identical_repeat_imports_nothing_new(self):
        text = HEADER + "\n" + row() + "\n"
        first = run(text)
        second = run(text)
        assert first.imported == 1
        assert second.imported == 0
        assert second.duplicate == 1
        assert Episode.objects.count() == 1

    def test_differing_content_is_a_conflict_and_never_overwrites(self):
        run(HEADER + "\n" + row(quality="good") + "\n")
        summary = run(HEADER + "\n" + row(quality="bad") + "\n")
        assert summary.conflict == 1
        assert summary.imported == 0
        # The stored row is untouched: create-only, never overwrite.
        assert Episode.objects.get().quality == "good"

    def test_case_differing_id_collides_with_the_stored_episode(self):
        """ep-00003 and EP-00003 are the same episode after normalization."""
        run(HEADER + "\n" + row(episode_id="EP-00003", task="fold towel") + "\n")
        summary = run(HEADER + "\n" + row(episode_id="ep-00003", task="wipe table") + "\n")
        assert summary.conflict == 1
        assert Episode.objects.count() == 1
        assert Episode.objects.get().task_name == "fold towel"

    def test_first_valid_occurrence_wins_within_one_file(self):
        """Order dependence is a documented policy, so it gets a test."""
        text = "\n".join(
            [
                HEADER,
                row(episode_id="EP-00007", task="pick cup"),
                row(episode_id="EP-00007", task="fold towel"),
                "",
            ]
        )
        summary = run(text)
        assert summary.imported == 1
        assert summary.conflict == 1
        assert Episode.objects.get().task_name == "pick cup"

    def test_counts_satisfy_the_documented_invariants(self):
        text = "\n".join(
            [
                HEADER,
                row(episode_id="EP-00001"),
                row(episode_id="EP-00002", duration="-5"),
                row(episode_id="EP-00001"),
                row(episode_id="EP-00003", quality="bad"),
                "",
            ]
        )
        summary = run(text)
        assert summary.processed == summary.imported + summary.skipped
        assert summary.skipped == (
            summary.duplicate + summary.conflict + summary.invalid
        )

    def test_issue_detail_is_capped_but_counts_are_not(self):
        rows = [row(episode_id=f"EP-{i:05d}", duration="-1") for i in range(10)]
        summary = csv_import.import_episodes(
            io.StringIO(HEADER + "\n" + "\n".join(rows) + "\n"), max_issues=3
        )
        assert summary.invalid == 10
        assert len(summary.issues) == 3
        assert summary.issues_truncated is True


class TestRowLimit:
    def test_exceeding_the_row_limit_aborts(self):
        rows = [row(episode_id=f"EP-{i:05d}") for i in range(5)]
        with pytest.raises(csv_import.ImportAborted, match="row limit"):
            csv_import.import_episodes(
                io.StringIO(HEADER + "\n" + "\n".join(rows) + "\n"), max_rows=3
            )


class TestSuppliedSeedFile:
    """Against the real messy export, not a sanitised fixture."""

    def test_seed_file_imports_with_the_recorded_totals(self):
        summary = csv_import.import_from_path(str(SEED_CSV))
        # Executed totals, recorded after actually running the importer.
        assert summary.processed == 189
        assert summary.imported == 172
        assert summary.skipped == 17
        assert summary.duplicate == 2
        assert summary.conflict == 2
        assert summary.invalid == 13
        assert summary.skipped_blank == 2
        assert Episode.objects.count() == 172

    def test_seed_file_is_idempotent(self):
        csv_import.import_from_path(str(SEED_CSV))
        second = csv_import.import_from_path(str(SEED_CSV))
        assert second.imported == 0
        assert Episode.objects.count() == 172

    def test_known_anomalies_are_handled_individually(self):
        csv_import.import_from_path(str(SEED_CSV))
        stored = {e.episode_id: e for e in Episode.objects.all()}

        # Quoted comma survived.
        assert stored["EP-90002"].task_name == "pick cup, then place"
        # Casing and padding normalized.
        assert stored["EP-00006"].task_name == "pick cup"
        assert stored["EP-00007"].task_name == "pick cup"
        assert stored["EP-00008"].robot_id == "arm-01"
        assert stored["EP-00009"].quality == "good"
        assert stored["EP-00010"].quality == "usable"
        # Day-first and space-separated timestamps.
        assert stored["EP-00014"].recorded_at.isoformat() == "2026-08-14T09:15:00+00:00"
        assert stored["EP-00013"].recorded_at.isoformat() == "2026-08-14T09:12:00+00:00"
        # Decimal duration.
        assert stored["EP-00018"].duration_seconds == Decimal("45.50")
        # Rejected rows are absent.
        for missing in ["EP-00016", "EP-00017", "EP-00019", "EP-00020", "EP-00021",
                        "EP-00023", "EP-00024", "EP-00025", "EP-90001", "EP-90003",
                        "EP-90004", "EP-90005"]:
            assert missing not in stored, missing
        # The conflicting lowercase duplicate never overwrote EP-00003.
        assert stored["EP-00003"].task_name == "fold towel"


class TestImportEndpoint:
    def test_staff_can_upload_and_get_a_report(self, login, operator, csrf):
        session = login(operator)
        upload = SimpleUploadedFile(
            "episodes.csv",
            (HEADER + "\n" + row() + "\n").encode(),
            content_type="text/csv",
        )
        response = session.post(
            "/api/episodes/import",
            data={"file": upload},
            headers={"x-csrftoken": csrf()},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["imported"] == 1
        assert body["processed"] == 1

    def test_client_cannot_import(self, login, client_a, csrf):
        session = login(client_a)
        upload = SimpleUploadedFile(
            "episodes.csv", (HEADER + "\n" + row() + "\n").encode(), content_type="text/csv"
        )
        response = session.post(
            "/api/episodes/import", data={"file": upload}, headers={"x-csrftoken": csrf()}
        )
        assert response.status_code == 403
        assert Episode.objects.count() == 0

    def test_missing_file_is_400(self, login, operator, csrf):
        session = login(operator)
        response = session.post(
            "/api/episodes/import", data={}, headers={"x-csrftoken": csrf()}
        )
        assert response.status_code == 400

    def test_bad_header_is_400_not_500(self, login, operator, csrf):
        session = login(operator)
        upload = SimpleUploadedFile(
            "wrong.csv", b"a,b,c\n1,2,3\n", content_type="text/csv"
        )
        response = session.post(
            "/api/episodes/import", data={"file": upload}, headers={"x-csrftoken": csrf()}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_file"

    def test_oversized_upload_is_413(self, login, operator, csrf, settings):
        settings.IMPORT_MAX_UPLOAD_BYTES = 10
        session = login(operator)
        upload = SimpleUploadedFile(
            "big.csv",
            (HEADER + "\n" + row() + "\n").encode(),
            content_type="text/csv",
        )
        response = session.post(
            "/api/episodes/import", data={"file": upload}, headers={"x-csrftoken": csrf()}
        )
        assert response.status_code == 413

    def test_api_and_cli_share_the_importer(self, login, operator, csrf, capsys):
        """One importer, two entry points: the CLI must agree with the API."""
        session = login(operator)
        upload = SimpleUploadedFile(
            "episodes.csv",
            (HEADER + "\n" + row(episode_id="EP-00042") + "\n").encode(),
            content_type="text/csv",
        )
        session.post(
            "/api/episodes/import", data={"file": upload}, headers={"x-csrftoken": csrf()}
        )
        assert Episode.objects.count() == 1

        # The same file through the CLI now reports a duplicate, not an import.
        call_command("import_episodes", str(SEED_CSV))
        captured = capsys.readouterr().out
        assert "processed=189" in captured

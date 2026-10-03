"""CLI episode import. Shares the importer with the HTTP endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from desk.services import csv_import


class Command(BaseCommand):
    help = "Import episode metadata from a CSV file."

    def add_arguments(self, parser) -> None:
        parser.add_argument("path", help="Path to the CSV file.")
        parser.add_argument(
            "--max-rows",
            type=int,
            default=None,
            help="Row limit. Raise it for large generated fixtures.",
        )
        parser.add_argument(
            "--report",
            default=None,
            help="Write every row issue to this path as JSONL (uncapped).",
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        try:
            summary = csv_import.import_from_path(
                str(path),
                max_rows=options["max_rows"],
                # The CLI reports every issue; only the API caps the list.
                max_issues=None if options["report"] else 1000,
            )
        except csv_import.ImportAborted as exc:
            # Non-zero exit so a broken file fails a pipeline loudly.
            raise CommandError(str(exc)) from exc

        counts = summary.as_dict()
        self.stdout.write(
            "processed={processed} imported={imported} skipped={skipped} "
            "duplicate={duplicate} conflict={conflict} invalid={invalid} "
            "blank={skipped_blank}".format(**counts)
        )

        if options["report"]:
            report_path = Path(options["report"])
            with report_path.open("w", encoding="utf-8") as handle:
                for line in csv_import.iter_issue_lines(summary.issues):
                    handle.write(line + "\n")
            self.stdout.write(f"Row issues written to {report_path}")
        elif summary.issues:
            self.stdout.write("")
            self.stdout.write("First row issues:")
            for issue in summary.issues[:20]:
                self.stdout.write(
                    f"  line {issue.line} "
                    f"{issue.episode_id or '(no id)'}: {issue.code} - {issue.reason}"
                )
            if len(summary.issues) > 20:
                self.stdout.write(f"  ... {len(summary.issues) - 20} more")

        if summary.issues_truncated:
            self.stdout.write(
                self.style.WARNING(
                    "Issue details were capped; use --report for the full list."
                )
            )
        self.stdout.write(self.style.SUCCESS(json.dumps(
            {key: value for key, value in counts.items() if key != "issues"}
        )))

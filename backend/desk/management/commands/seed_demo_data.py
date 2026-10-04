"""Explicit demo population through the real importer and domain services."""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from config.errors import WorkflowConflict
from desk.models import DatasetRequest, DemoSeedRecord, Episode, RequestStatus
from desk.services import assignments, csv_import, workflow

# These clean pick-cup rows exist in the supplied CSV. Never allocate unrelated
# inventory just because it happens to have the same task name.
EPISODE_IDS = [
    f"EP-{number:05d}" for number in
    (1, 10, 32, 40, 42, 51, 52, 54, 57, 59, 66, 92, 138, 141, 177, 180)
]
CLIENTS = ("client-a@example.com", "client-b@example.com")


class Command(BaseCommand):
    help = "Opt in to small demo requests for the two public demo clients."

    def handle(self, *args, **options):
        created = skipped = conflicting = 0
        # Serialize concurrent seed runs on the same existing demo operator.
        # Each request has its own savepoint so a collision leaves it untouched.
        with transaction.atomic():
            users = {
                user.email: user for user in User.objects.select_for_update()
                .filter(email__in=(*CLIENTS, "ops1@example.com")).order_by("email")
            }
            expected = {
                CLIENTS[0]: ("client", "Acme Robotics", "Acme Robotics"),
                CLIENTS[1]: ("client", "Beta Labs", "Beta Labs"),
                "ops1@example.com": ("operator", "Olu Operator", ""),
            }
            for email, identity in expected.items():
                user = users.get(email)
                if (user is None or not user.is_active or
                        (user.role, user.name, user.organisation) != identity or
                        email == settings.PERSONAL_ADMIN_EMAIL):
                    raise CommandError(
                        f"Demo account missing or conflicting: {email}. "
                        "No demo data changed. Run seed_users; inspect existing accounts manually."
                    )
            try:
                summary = csv_import.import_from_path(
                    str(Path(settings.REPO_ROOT) / "seed" / "episodes.csv"), max_issues=None
                )
            except csv_import.ImportAborted as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(
                f"Episodes: {summary.imported} created, {summary.skipped} skipped "
                f"({summary.conflict} conflicting, {summary.invalid} invalid)."
            )
            excluded = {issue.episode_id for issue in summary.issues if issue.code == "conflict"}
            operator = users["ops1@example.com"]
            for email in CLIENTS:
                for status in RequestStatus.values:
                    key = f"demo-v1/{email}/{status}"
                    notes = f"Public demo: {key}"
                    try:
                        with transaction.atomic():
                            record = DemoSeedRecord.objects.select_related("request").filter(pk=key).first()
                            if record:
                                if record.request.client_id != users[email].pk:
                                    raise WorkflowConflict("Registry owner conflicts with the demo client.")
                                # Human edits and later workflow changes are preserved, never reset.
                                skipped += 1
                                continue
                            if DatasetRequest.objects.filter(notes=notes).exists():
                                raise WorkflowConflict("Seed identifier exists without registry ownership.")
                            request = workflow.create_request(
                                client=users[email], task_name="pick cup", episodes_requested=2,
                                deadline=timezone.localdate() + timedelta(days=30), notes=notes,
                            )
                            if status != RequestStatus.SUBMITTED:
                                workflow.transition(request_id=request.pk, actor=operator, target="in_progress")
                                needed = 1 if status == RequestStatus.IN_PROGRESS else 2
                                ids = list(Episode.objects.filter(
                                    episode_id__in=EPISODE_IDS, task_name="pick cup",
                                    quality__in=("good", "usable"), assignment__isnull=True,
                                ).exclude(episode_id__in=excluded).order_by("episode_id")
                                    .values_list("pk", flat=True)[:needed])
                                if len(ids) != needed:
                                    raise WorkflowConflict("Not enough unreserved supplied episodes; existing allocations preserved.")
                                assignments.assign_episodes(request_id=request.pk, actor=operator, episode_ids=ids)
                            if status in ("delivered", "accepted", "rejected"):
                                workflow.transition(request_id=request.pk, actor=operator, target="delivered")
                            if status in ("accepted", "rejected"):
                                workflow.transition(
                                    request_id=request.pk, actor=users[email], target=status,
                                    reason="Please review the selection." if status == "rejected" else "",
                                )
                            DemoSeedRecord.objects.create(key=key, request=request)
                            created += 1
                    except WorkflowConflict as exc:
                        conflicting += 1
                        self.stdout.write(f"Conflict {key}: {exc}")
        self.stdout.write(f"Demo requests: {created} created, {skipped} skipped, {conflicting} conflicting.")
        self.stdout.write("Assignments enqueue normal export jobs; the running worker may change their statuses.")

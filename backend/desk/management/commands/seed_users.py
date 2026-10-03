"""Seed the demo accounts from seed/users.json.

Re-running is safe and non-destructive: an existing account keeps its current
password, role and active flag. That matters because this command runs on every
container start, and resetting a password or silently reactivating an account
an admin had deactivated would be a real security regression.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role, User

DEFAULT_SEED = Path(settings.REPO_ROOT) / "seed" / "users.json"


class Command(BaseCommand):
    help = "Create the demo accounts listed in seed/users.json (idempotent)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--path", default=str(DEFAULT_SEED), help="Path to users.json."
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"Seed file not found: {path}")

        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"{path} is not valid JSON: {exc}") from exc

        created = skipped = 0
        with transaction.atomic():
            for entry in entries:
                email = User.objects.normalize_email(entry.get("email"))
                if not email:
                    raise CommandError("A seed entry is missing its email.")
                if User.objects.filter(email=email).exists():
                    skipped += 1
                    continue
                role = entry.get("role", Role.CLIENT)
                if role not in {choice.value for choice in Role}:
                    raise CommandError(f"{email}: unknown role {role!r}.")
                User.objects.create_user(
                    email=email,
                    # Hashed by set_password; the plaintext from the seed file
                    # is never stored.
                    password=entry["password"],
                    name=entry.get("name", email),
                    role=role,
                    organisation=entry.get("organisation", ""),
                )
                created += 1

            personal_created = self._seed_personal_admin()

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo accounts: {created} created, {skipped} already present."
            )
        )
        if personal_created:
            self.stdout.write(
                self.style.SUCCESS("Personal admin account created from environment.")
            )

    def _seed_personal_admin(self) -> bool:
        """Create the optional personal admin, only if both env vars are set.

        The password is read from the environment and passed straight to
        set_password. It is never logged, echoed or written to a file, and the
        account is skipped entirely when either variable is absent so demo
        startup works without it.
        """
        email = User.objects.normalize_email(settings.PERSONAL_ADMIN_EMAIL)
        password = settings.PERSONAL_ADMIN_PASSWORD
        if not email or not password:
            if email or password:
                self.stdout.write(
                    self.style.WARNING(
                        "Skipping personal admin: set both PERSONAL_ADMIN_EMAIL "
                        "and PERSONAL_ADMIN_PASSWORD."
                    )
                )
            return False
        if User.objects.filter(email=email).exists():
            # Never overwrite on rerun, including the password.
            return False
        User.objects.create_user(
            email=email,
            password=password,
            name=settings.PERSONAL_ADMIN_NAME,
            role=Role.ADMIN,
        )
        return True

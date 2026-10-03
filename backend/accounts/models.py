"""Custom email-identified user with a mutually exclusive role."""

from __future__ import annotations

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class Role(models.TextChoices):
    CLIENT = "client", "Client"
    OPERATOR = "operator", "Operator"
    ADMIN = "admin", "Admin"


STAFF_ROLES = frozenset({Role.OPERATOR, Role.ADMIN})


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def normalize_email(self, email: str | None) -> str:
        """Lowercase the whole address, not just the domain.

        BaseUserManager only lowercases the domain part. Logins here are
        case-insensitive on the full address, so the stored form has to be
        fully normalized or `unique=True` would let Ada@x and ada@x coexist.
        """
        return (email or "").strip().lower()

    def create_user(
        self,
        email: str,
        password: str | None = None,
        *,
        role: str = Role.CLIENT,
        name: str = "",
        organisation: str = "",
        **extra: object,
    ) -> User:
        email = self.normalize_email(email)
        if not email:
            raise ValueError("A user requires an email address.")
        user = self.model(
            email=email, role=role, name=name, organisation=organisation, **extra
        )
        # set_unusable_password() when password is None: no blank-password login.
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email: str, password: str | None = None, **extra: object
    ) -> User:
        """Present for createsuperuser only.

        is_superuser is deliberately absent from this model: the business API
        derives every permission from `role`, so there is no flag that can
        silently bypass a role check.
        """
        extra.setdefault("role", Role.ADMIN)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=254)
    name = models.CharField(max_length=150)
    organisation = models.CharField(max_length=150, blank=True, default="")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CLIENT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        ordering = ["email"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=[choice.value for choice in Role]),
                name="user_role_valid",
            )
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args: object, **kwargs: object) -> None:
        self.email = UserManager().normalize_email(self.email)
        super().save(*args, **kwargs)

    @property
    def is_staff_member(self) -> bool:
        """Operator or admin. Named to avoid colliding with Django's is_staff."""
        return self.role in STAFF_ROLES

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_client(self) -> bool:
        return self.role == Role.CLIENT

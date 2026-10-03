"""Account serializers. No serializer here exposes `password` on read."""

from __future__ import annotations

from django.contrib.auth import password_validation
from rest_framework import serializers

from accounts.models import Role, User


class UserSerializer(serializers.ModelSerializer):
    """Read shape. The password hash is not a declared field anywhere."""

    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "organisation", "is_active", "created_at"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        # write_only keeps it out of any echoed representation, and
        # trim_whitespace=False avoids silently altering a valid password.
        write_only=True,
        trim_whitespace=False,
        max_length=256,
        style={"input_type": "password"},
    )


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)

    class Meta:
        model = User
        fields = ["name", "email", "password", "role", "organisation"]

    def validate_email(self, value: str) -> str:
        normalized = User.objects.normalize_email(value)
        if User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalized

    def validate_password(self, value: str) -> str:
        # Django's configured validators: length, commonness, all-numeric.
        password_validation.validate_password(value)
        return value

    def validate_role(self, value: str) -> str:
        if value not in {choice.value for choice in Role}:
            raise serializers.ValidationError("Choose client, operator or admin.")
        return value


class UserUpdateSerializer(serializers.Serializer):
    """Role and active flag only.

    Email, name and password are deliberately not editable here: changing an
    identity out from under an audit trail needs more thought than an MVP
    PATCH, and it is called out as a simplification in NOTES.md.
    """

    role = serializers.ChoiceField(choices=Role.choices, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("Provide role and/or is_active.")
        return attrs

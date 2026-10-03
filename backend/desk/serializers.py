"""Desk serializers."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from desk.models import (
    Assignment,
    DatasetRequest,
    Episode,
    ExportJob,
    RequestStatus,
    StatusHistory,
)
from desk.normalize import normalize_task_name


class EpisodeSerializer(serializers.ModelSerializer):
    # DecimalField renders as a quoted string by default, which keeps the exact
    # value intact instead of handing the browser a float to round.
    duration_seconds = serializers.DecimalField(max_digits=8, decimal_places=2)
    assigned_request_id = serializers.SerializerMethodField()

    class Meta:
        model = Episode
        fields = [
            "id",
            "episode_id",
            "robot_id",
            "task_name",
            "recorded_at",
            "duration_seconds",
            "operator_name",
            "quality",
            "imported_at",
            "assigned_request_id",
        ]
        read_only_fields = fields

    def get_assigned_request_id(self, obj: Episode) -> str | None:
        """Staff-only. Clients never see global allocation state."""
        request = self.context.get("request")
        if request is None or not request.user.is_staff_member:
            return None
        link = getattr(obj, "assignment", None)
        return str(link.request_id) if link else None


class ExportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportJob
        fields = ["status", "attempts", "max_attempts", "last_error", "completed_at"]
        read_only_fields = fields


class AssignmentSerializer(serializers.ModelSerializer):
    episode = EpisodeSerializer(read_only=True)
    export_job = ExportJobSerializer(read_only=True)
    assigned_by_name = serializers.CharField(source="assigned_by.name", read_only=True)

    class Meta:
        model = Assignment
        fields = ["id", "episode", "export_job", "assigned_by_name", "assigned_at"]
        read_only_fields = fields


class StatusHistorySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.name", read_only=True)
    actor_id = serializers.UUIDField(source="actor.id", read_only=True)

    class Meta:
        model = StatusHistory
        fields = [
            "id",
            "previous_status",
            "new_status",
            "actor_id",
            "actor_name",
            "reason",
            "created_at",
        ]
        read_only_fields = fields


class DatasetRequestSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_id = serializers.UUIDField(source="client.id", read_only=True)
    assigned_count = serializers.IntegerField(read_only=True)
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = DatasetRequest
        fields = [
            "id",
            "client_id",
            "client_name",
            "task_name",
            "episodes_requested",
            "deadline",
            "notes",
            "status",
            "assigned_count",
            "allowed_actions",
            "created_at",
            "updated_at",
            "first_delivered_at",
        ]
        read_only_fields = fields

    def get_allowed_actions(self, obj: DatasetRequest) -> list[str]:
        from desk.services.workflow import allowed_actions

        request = self.context.get("request")
        if request is None:
            return []
        count = getattr(obj, "assigned_count", None)
        if count is None:
            count = obj.assignments.count()
        return allowed_actions(request.user, obj, count)


class DatasetRequestCreateSerializer(serializers.Serializer):
    """Client-supplied fields only.

    owner and status are absent on purpose: the view takes the owner from the
    session and the service sets the status. A payload carrying client_id or
    status is rejected below rather than quietly ignored, so a caller is never
    misled into thinking it set them.
    """

    task_name = serializers.CharField(max_length=120, min_length=1)
    episodes_requested = serializers.IntegerField(min_value=1, max_value=100_000)
    deadline = serializers.DateField()
    notes = serializers.CharField(
        max_length=4000, required=False, allow_blank=True, default=""
    )

    _REJECTED_FIELDS = ("client", "client_id", "owner", "owner_id", "status", "id")

    def validate(self, attrs: dict) -> dict:
        supplied = set(self.initial_data or {})
        intruders = sorted(supplied.intersection(self._REJECTED_FIELDS))
        if intruders:
            raise serializers.ValidationError(
                {
                    field: ["This field is set by the server and cannot be supplied."]
                    for field in intruders
                }
            )
        return attrs

    def validate_task_name(self, value: str) -> str:
        normalized = normalize_task_name(value)
        if not normalized:
            raise serializers.ValidationError("Enter a task name.")
        return normalized

    def validate_deadline(self, value: date) -> date:
        # Judged against the client's calendar day in Kigali, not the server's
        # UTC day: at 01:00 Kigali the UTC date is still yesterday, and a
        # deadline of "today" must not be rejected as past.
        today_local = timezone.now().astimezone(
            ZoneInfo(settings.BUSINESS_TIME_ZONE)
        ).date()
        if value < today_local:
            raise serializers.ValidationError(
                f"Choose a deadline on or after {today_local.isoformat()}."
            )
        return value


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RequestStatus.choices)
    reason = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class AssignmentCreateSerializer(serializers.Serializer):
    episode_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        max_length=settings.ASSIGNMENT_MAX_PER_CALL,
    )


class AnalyticsQuerySerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs: dict) -> dict:
        start, end = attrs["start"], attrs["end"]
        if start > end:
            raise serializers.ValidationError(
                {"start": ["The start date must not be after the end date."]}
            )
        span_days = (end - start).days + 1
        if span_days > settings.ANALYTICS_MAX_RANGE_DAYS:
            raise serializers.ValidationError(
                {
                    "end": [
                        f"Choose a range of at most "
                        f"{settings.ANALYTICS_MAX_RANGE_DAYS} days."
                    ]
                }
            )
        return attrs

"""Desk API views.

Ownership is enforced by narrowing the queryset, not by checking after the
fetch. A client asking for another client's request id gets 404 from the
filtered queryset itself, which also means request ids are not an oracle for
"this exists but isn't yours".
"""

from __future__ import annotations

import io
import logging

from django.conf import settings
from django.db.models import Count, QuerySet
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsClient, IsStaff
from config.errors import UploadTooLarge
from desk.models import (
    ASSIGNABLE_QUALITIES,
    Assignment,
    DatasetRequest,
    Episode,
    Quality,
)
from desk.pagination import DeskPagination
from desk.serializers import (
    AnalyticsQuerySerializer,
    AssignmentCreateSerializer,
    AssignmentSerializer,
    DatasetRequestCreateSerializer,
    DatasetRequestSerializer,
    EpisodeSerializer,
    StatusHistorySerializer,
    TransitionSerializer,
)
from desk.services import analytics as analytics_service
from desk.services import assignments as assignment_service
from desk.services import csv_import
from desk.services import workflow as workflow_service

logger = logging.getLogger("desk.api")


def visible_requests(user) -> QuerySet[DatasetRequest]:
    """The request rows this user may see at all.

    One place, used by list, detail, history, transitions and assignments, so
    there is no endpoint where the ownership filter was forgotten.
    """
    queryset = (
        DatasetRequest.objects.select_related("client")
        # assigned_count in one aggregate instead of a COUNT per row.
        .annotate(assigned_count=Count("assignments"))
        # Explicit and total: annotate() drops Meta.ordering, and paginating an
        # unordered queryset lets rows repeat or disappear between pages. The
        # id tiebreak keeps the order stable when created_at values collide.
        .order_by("-created_at", "-id")
    )
    if user.is_staff_member:
        return queryset
    return queryset.filter(client=user)


class RequestListCreateView(APIView):
    def get(self, request):
        queryset = visible_requests(request.user)

        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        task = request.query_params.get("task_name", "").strip()
        if task:
            queryset = queryset.filter(task_name__icontains=task)
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(task_name__icontains=search)

        paginator = DeskPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = DatasetRequestSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        # Clients only. An operator or admin creating a request on a client's
        # behalf would need an owner field, which this MVP does not accept.
        if not IsClient().has_permission(request, self):
            return Response(
                {
                    "error": {
                        "code": "forbidden",
                        "message": "Only client accounts can create requests.",
                    },
                    "request_id": getattr(request, "request_id", None),
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = DatasetRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = workflow_service.create_request(
            client=request.user, **serializer.validated_data
        )
        instance = visible_requests(request.user).get(pk=created.pk)
        return Response(
            DatasetRequestSerializer(instance, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class RequestDetailView(APIView):
    def get(self, request, request_id):
        instance = _get_visible_or_404(request.user, request_id)
        return Response(
            DatasetRequestSerializer(instance, context={"request": request}).data
        )


class RequestHistoryView(APIView):
    def get(self, request, request_id):
        instance = _get_visible_or_404(request.user, request_id)
        history = instance.history.select_related("actor").order_by("created_at", "id")
        return Response(StatusHistorySerializer(history, many=True).data)


class RequestTransitionView(APIView):
    def post(self, request, request_id):
        # Confirm visibility first so a client probing someone else's id gets
        # 404 rather than a workflow error that confirms the row exists.
        _get_visible_or_404(request.user, request_id)
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = workflow_service.transition(
            request_id=request_id,
            actor=request.user,
            target=serializer.validated_data["status"],
            reason=serializer.validated_data.get("reason", ""),
        )
        logger.info(
            "request transition",
            extra={
                "request_id_value": str(request_id),
                "new_status": result.request.status,
                "actor_id": str(request.user.pk),
            },
        )
        instance = visible_requests(request.user).get(pk=request_id)
        return Response(
            DatasetRequestSerializer(instance, context={"request": request}).data
        )


class RequestAssignmentsView(APIView):
    def get(self, request, request_id):
        instance = _get_visible_or_404(request.user, request_id)
        links = (
            Assignment.objects.filter(request=instance)
            # Eager loading: without these the per-episode export job and the
            # assigning user would each cost one query per row.
            .select_related("episode", "assigned_by", "export_job")
            .order_by("assigned_at", "id")
        )
        return Response(
            {
                "results": AssignmentSerializer(
                    links, many=True, context={"request": request}
                ).data,
                "assigned_count": links.count(),
                "episodes_requested": instance.episodes_requested,
            }
        )

    def post(self, request, request_id):
        if not IsStaff().has_permission(request, self):
            return Response(
                {
                    "error": {
                        "code": "forbidden",
                        "message": "Operator or administrator access is required.",
                    },
                    "request_id": getattr(request, "request_id", None),
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = assignment_service.assign_episodes(
            request_id=request_id,
            actor=request.user,
            episode_ids=serializer.validated_data["episode_ids"],
        )
        return Response(
            {
                "created_ids": [str(link.id) for link in result.created],
                "existing_ids": [str(link.id) for link in result.existing],
                "assigned_count": result.assigned_count,
                "episodes_requested": result.episodes_requested,
            },
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class AssignmentDetailView(APIView):
    permission_classes = [IsStaff]

    def delete(self, request, request_id, assignment_id):
        remaining = assignment_service.remove_assignment(
            request_id=request_id, assignment_id=assignment_id, actor=request.user
        )
        logger.info(
            "assignment removed",
            extra={"request_id_value": str(request_id), "remaining": remaining},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class EpisodeListView(APIView):
    """Staff-only episode inventory.

    Clients have no route to the global episode list; they see only the
    episodes linked to their own request, via /requests/{id}/assignments.
    """

    permission_classes = [IsStaff]

    def get(self, request):
        queryset = Episode.objects.select_related("assignment").all()

        task = request.query_params.get("task_name", "").strip().lower()
        if task:
            queryset = queryset.filter(task_name=task)
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(episode_id__icontains=search) | queryset.filter(
                robot_id__icontains=search
            )
        quality = request.query_params.get("quality", "").strip().lower()
        if quality in {choice.value for choice in Quality}:
            queryset = queryset.filter(quality=quality)

        available = request.query_params.get("available", "").strip().lower()
        if available in {"true", "1", "yes"}:
            # Unreserved and eligible: 'bad' episodes can never be assigned.
            queryset = queryset.filter(
                assignment__isnull=True, quality__in=ASSIGNABLE_QUALITIES
            )

        queryset = queryset.distinct().order_by("episode_id", "id")
        paginator = DeskPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            EpisodeSerializer(page, many=True, context={"request": request}).data
        )


class EpisodeImportView(APIView):
    permission_classes = [IsStaff]
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Attach a CSV file in the 'file' field.",
                    },
                    "request_id": getattr(request, "request_id", None),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > settings.IMPORT_MAX_UPLOAD_BYTES:
            limit_mb = settings.IMPORT_MAX_UPLOAD_BYTES // (1024 * 1024)
            raise UploadTooLarge(f"The file exceeds the {limit_mb} MB limit.")

        # Decoded through a text wrapper so csv.reader streams the upload
        # rather than the whole file being materialised as one string.
        wrapper = io.TextIOWrapper(upload.file, encoding="utf-8-sig", newline="")
        try:
            summary = csv_import.import_episodes(wrapper)
        except csv_import.ImportAborted as exc:
            return Response(
                {
                    "error": {"code": "invalid_file", "message": str(exc)},
                    "request_id": getattr(request, "request_id", None),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        finally:
            wrapper.detach()

        logger.info(
            "episode import",
            extra={
                "actor_id": str(request.user.pk),
                "processed": summary.processed,
                "imported": summary.imported,
                "skipped": summary.skipped,
            },
        )
        return Response(summary.as_dict())


class AnalyticsView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        serializer = AnalyticsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        window = analytics_service.Window(
            start=serializer.validated_data["start"], end=serializer.validated_data["end"]
        )
        return Response(analytics_service.build_report(window))


def _get_visible_or_404(user, request_id) -> DatasetRequest:
    from rest_framework.exceptions import NotFound

    instance = visible_requests(user).filter(pk=request_id).first()
    if instance is None:
        # 404 for both "no such request" and "not yours": the two are
        # indistinguishable to the caller by design.
        raise NotFound("Not found.")
    return instance

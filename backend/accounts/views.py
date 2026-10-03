"""Authentication and admin user management endpoints."""

from __future__ import annotations

import logging

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts import services
from accounts.models import User
from accounts.permissions import IsActiveAuthenticated, IsAdmin
from accounts.serializers import (
    LoginSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from desk.pagination import DeskPagination

logger = logging.getLogger("desk.auth")


class LoginThrottle(ScopedRateThrottle):
    """Throttles by IP for anonymous callers.

    Documented limitation: the default cache is per-process, so with several
    API workers the effective limit is per worker. A shared cache (Redis or the
    database) would be needed for a real limit; that is noted in NOTES.md.
    """

    scope = "login"


@method_decorator(ensure_csrf_cookie, name="get")
class CSRFView(APIView):
    """Hand an anonymous caller a CSRF cookie so it can post to /auth/login.

    This is the single anonymous endpoint. It is an explicit, documented
    exception to "login required for every action": it issues no session, reads
    no data, and returns only a token bound to the caller's own cookie.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class LoginView(APIView):
    """Session login. CSRF is enforced here too, not just on authenticated routes."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = User.objects.normalize_email(serializer.validated_data["email"])
        password = serializer.validated_data["password"]

        user = authenticate(request, username=email, password=password)
        if user is None or not user.is_active:
            # One generic message for unknown email, wrong password and
            # deactivated account, so the response cannot enumerate accounts.
            logger.info("login rejected", extra={"outcome": "invalid_credentials"})
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Incorrect email or password.",
                    },
                    "request_id": getattr(request, "request_id", None),
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # login() cycles the session key, so a pre-login fixated session id is
        # useless to an attacker.
        login(request, user)
        logger.info("login accepted", extra={"user_id": str(user.pk)})
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserListCreateView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        queryset = User.objects.all().order_by("email")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(email__icontains=search) | queryset.filter(
                name__icontains=search
            )
        paginator = DeskPagination()
        page = paginator.paginate_queryset(queryset.distinct(), request, view=self)
        return paginator.get_paginated_response(UserSerializer(page, many=True).data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.create_user(actor=request.user, **serializer.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, user_id):
        serializer = UserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.update_user(
            actor=request.user, user_id=user_id, **serializer.validated_data
        )
        return Response(UserSerializer(user).data)


def probe_database() -> None:
    """Round-trip the database. Raises on any failure.

    A separate function so a test can simulate an unreachable database
    without patching the connection that the session backend also needs to
    authenticate the request.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


class HealthView(APIView):
    """Authenticated health check.

    Deliberately not anonymous: the brief wants login required for everything
    but login. Container readiness uses pg_isready instead of this endpoint,
    so nothing depends on an unauthenticated bypass.
    """

    permission_classes = [IsActiveAuthenticated]

    def get(self, request):
        try:
            probe_database()
        except Exception:
            # Sanitized deliberately. The error text can carry the host, port,
            # database name and sometimes credentials from the DSN, none of
            # which belongs in a client response.
            logger.warning("health check failed", extra={"component": "database"})
            return Response(
                {"status": "unavailable", "database": "unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "ok"})

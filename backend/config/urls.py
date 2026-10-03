"""URL routing. Everything lives under /api except /health."""

from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts import views as account_views
from desk import views as desk_views

api_patterns = [
    path("auth/csrf", account_views.CSRFView.as_view(), name="csrf"),
    path("auth/login", account_views.LoginView.as_view(), name="login"),
    path("auth/logout", account_views.LogoutView.as_view(), name="logout"),
    path("auth/me", account_views.MeView.as_view(), name="me"),
    path("requests", desk_views.RequestListCreateView.as_view(), name="request-list"),
    path(
        "requests/<uuid:request_id>",
        desk_views.RequestDetailView.as_view(),
        name="request-detail",
    ),
    path(
        "requests/<uuid:request_id>/history",
        desk_views.RequestHistoryView.as_view(),
        name="request-history",
    ),
    path(
        "requests/<uuid:request_id>/transitions",
        desk_views.RequestTransitionView.as_view(),
        name="request-transitions",
    ),
    path(
        "requests/<uuid:request_id>/assignments",
        desk_views.RequestAssignmentsView.as_view(),
        name="request-assignments",
    ),
    path(
        "requests/<uuid:request_id>/assignments/<uuid:assignment_id>",
        desk_views.AssignmentDetailView.as_view(),
        name="assignment-detail",
    ),
    path("episodes", desk_views.EpisodeListView.as_view(), name="episode-list"),
    path("episodes/import", desk_views.EpisodeImportView.as_view(), name="episode-import"),
    path("analytics", desk_views.AnalyticsView.as_view(), name="analytics"),
    path("users", account_views.UserListCreateView.as_view(), name="user-list"),
    path("users/<uuid:user_id>", account_views.UserDetailView.as_view(), name="user-detail"),
    # Schema and docs require a session: SPECTACULAR_SETTINGS sets
    # SERVE_PERMISSIONS, so the contract is not published anonymously.
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

urlpatterns = [
    path("api/", include((api_patterns, "api"))),
    # Outside the /api prefix, per the contract. Still authenticated.
    path("health", account_views.HealthView.as_view(), name="health"),
]

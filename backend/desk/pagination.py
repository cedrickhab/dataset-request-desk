"""Shared pagination: page_size default 25, hard max 100."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class DeskPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

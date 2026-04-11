"""Staff inbox API endpoint."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from django.core.paginator import EmptyPage, Paginator
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.player_submissions.permissions import IsStaffUser
from world.staff_inbox.filters import StaffInboxFilterSerializer
from world.staff_inbox.services import (
    get_account_submission_history,
    get_staff_inbox,
)
from world.staff_inbox.types import InboxItem


class StaffInboxView(APIView):
    """Aggregated inbox of items needing staff attention."""

    permission_classes = [IsStaffUser]

    def get(self, request: Request) -> Response:
        filter_serializer = StaffInboxFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        data = filter_serializer.validated_data
        categories = data.get("categories")
        page_num = data["page"]
        page_size = data["page_size"]

        items = get_staff_inbox(categories=categories)
        paginator = Paginator(items, page_size)
        try:
            page = paginator.page(page_num)
        except EmptyPage:
            page = paginator.page(paginator.num_pages) if paginator.num_pages > 0 else None

        results = [asdict(item) for item in page.object_list] if page else []
        next_page = page.next_page_number() if page and page.has_next() else None
        prev_page = page.previous_page_number() if page and page.has_previous() else None
        current_page = page.number if page else page_num

        # Match the StandardResultsSetPagination shape used across the
        # rest of the project (see world.stories.pagination).
        return Response(
            {
                "count": paginator.count,
                "next": self._build_page_url(request, next_page) if next_page else None,
                "previous": (self._build_page_url(request, prev_page) if prev_page else None),
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "current_page": current_page,
                "results": results,
            },
        )

    def _build_page_url(self, request: Request, page: int) -> str:
        """Build the URL for a specific page, preserving query params."""
        params = request.query_params.copy()
        params["page"] = str(page)
        return f"{request.build_absolute_uri(request.path)}?{params.urlencode()}"


class AccountHistoryView(APIView):
    """Staff-only view of all submissions related to an account."""

    permission_classes = [IsStaffUser]

    def get(self, request: Request, account_id: int) -> Response:
        history = get_account_submission_history(account_id=account_id)
        return Response(
            {key: self._serialize_category(entry) for key, entry in history.items()},
        )

    def _serialize_category(self, entry: dict[str, Any]) -> dict[str, Any]:
        items: list[InboxItem] = entry["items"]
        return {
            "items": [asdict(i) for i in items],
            "total": entry["total"],
            "truncated": entry["truncated"],
        }

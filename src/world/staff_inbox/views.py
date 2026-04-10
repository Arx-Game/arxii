"""Staff inbox API endpoint."""

from __future__ import annotations

from dataclasses import asdict

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.staff_inbox.filters import StaffInboxFilterSerializer
from world.staff_inbox.services import get_staff_inbox


class IsStaffUser(BasePermission):
    """Only staff users can access the inbox."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user and request.user.is_authenticated and request.user.is_staff,
        )


class StaffInboxView(APIView):
    """Aggregated inbox of items needing staff attention."""

    permission_classes = [IsStaffUser]

    def get(self, request: Request) -> Response:
        filter_serializer = StaffInboxFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        categories = filter_serializer.validated_data.get("categories")
        items = get_staff_inbox(categories=categories)
        return Response(
            {
                "count": len(items),
                "results": [asdict(item) for item in items],
            },
        )

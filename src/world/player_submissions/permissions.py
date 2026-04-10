"""Permission classes for player submission endpoints."""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsAuthenticatedCanSubmit(BasePermission):
    """Any authenticated user can submit (create) a submission."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)


class IsStaffForReview(BasePermission):
    """Only staff can list/retrieve/update submissions.

    First-PR scope: all review tiers are staff-only. Delegation to
    senior GMs or GM groups comes later when the GM system exists.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user and request.user.is_authenticated and request.user.is_staff,
        )

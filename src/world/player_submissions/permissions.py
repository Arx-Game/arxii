"""Permission classes for player submission endpoints."""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsAuthenticatedCanSubmit(BasePermission):
    """Any authenticated user can submit (create) a submission."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)


class IsStaffUser(BasePermission):
    """Only staff can access staff-only endpoints.

    First-PR scope: all review tiers are staff-only. Delegation to
    senior GMs or GM groups comes later when the GM system exists.

    Shared canonical implementation — imported by both player_submissions
    and staff_inbox to avoid duplication.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user and request.user.is_authenticated and request.user.is_staff,
        )

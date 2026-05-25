"""Permission classes for the missions DRF API.

Per Phase D's plan all mission-authoring endpoints are staff-only.
``IsStaff`` is the single guard — paired with DRF's IsAuthenticated for
the 401-vs-403 split — applied uniformly to every viewset in the
missions URL surface. Player-facing offering surfaces (not yet built;
that lands when the consumer side ships) will use a separate permission
class.
"""

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class IsStaff(permissions.BasePermission):
    """Allow only authenticated staff users (request.user.is_staff)."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)

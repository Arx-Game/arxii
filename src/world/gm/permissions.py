"""GM system permission classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

from world.gm.models import GMProfile

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


class IsGM(BasePermission):
    """Require the requesting user to have a GMProfile.

    When this permission passes, views can safely access ``request.user.gm_profile``
    without try/except.
    """

    message = "You must be a GM to use this endpoint."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        try:
            request.user.gm_profile  # noqa: B018  - side effect: triggers reverse lookup
        except GMProfile.DoesNotExist:
            return False
        return True


class IsGMOrStaff(BasePermission):
    """Pass if user has a GMProfile OR is staff.

    Use on endpoints that staff should access in addition to GMs (e.g. viewing
    application queues, revoking invites). Views must branch on ``is_staff``
    for staff-specific behavior where needed.
    """

    message = "You must be a GM or staff to use this endpoint."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_staff:
            return True
        try:
            request.user.gm_profile  # noqa: B018
        except GMProfile.DoesNotExist:
            return False
        return True

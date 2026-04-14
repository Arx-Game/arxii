"""Shared API permission classes."""

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.roster.models import RosterTenure


class IsCharacterOwner(permissions.BasePermission):
    """Validates the requesting account has an active RosterTenure for
    the character identified by 'character_id' in the URL kwargs."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.user.is_staff:
            return True
        character_id = view.kwargs.get("character_id")
        if character_id is None:
            return False
        try:
            return RosterTenure.objects.filter(
                roster_entry__character_sheet_id=character_id,
                player_data__account=request.user,
                start_date__isnull=False,
                end_date__isnull=True,
            ).exists()
        except AttributeError:
            return False

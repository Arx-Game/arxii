from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from evennia_extensions.models import PlayerData
from world.roster.models import RosterEntry
from world.scenes.interaction_services import can_view_interaction
from world.scenes.models import Interaction


def get_account_roster_entries(request: Request) -> list[RosterEntry]:
    """Return all roster entries belonging to the authenticated user's account.

    Path: Account -> PlayerData -> RosterTenure (current) -> RosterEntry
    """
    user = request.user
    if not user.is_authenticated:
        return []
    try:
        player_data = PlayerData.objects.get(account=user)
    except PlayerData.DoesNotExist:
        return []
    return list(
        RosterEntry.objects.filter(
            tenures__player_data=player_data,
            tenures__end_date__isnull=True,
        )
    )


class CanViewInteraction(permissions.BasePermission):
    """Permission to check if user can view a specific interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        roster_entries = get_account_roster_entries(request)
        if not roster_entries:
            return False

        return any(
            can_view_interaction(obj, re, is_staff=request.user.is_staff) for re in roster_entries
        )


class IsInteractionWriter(permissions.BasePermission):
    """Only the writer can modify/delete their interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        roster_entries = get_account_roster_entries(request)
        if not roster_entries:
            return False
        roster_entry_ids = {re.pk for re in roster_entries}
        return obj.roster_entry_id in roster_entry_ids

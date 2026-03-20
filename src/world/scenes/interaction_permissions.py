from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.scenes.interaction_services import can_view_interaction
from world.scenes.interaction_utils import get_roster_entry_from_request
from world.scenes.models import Interaction


class CanViewInteraction(permissions.BasePermission):
    """Permission to check if user can view a specific interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        roster_entry = get_roster_entry_from_request(request)
        if roster_entry is None:
            return False

        return can_view_interaction(
            obj,
            roster_entry,
            is_staff=request.user.is_staff,
        )


class IsInteractionWriter(permissions.BasePermission):
    """Only the writer can modify/delete their interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        roster_entry = get_roster_entry_from_request(request)
        if roster_entry is None:
            return False
        return obj.roster_entry_id == roster_entry.pk

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.scenes.interaction_services import can_view_interaction
from world.scenes.models import Interaction


class CanViewInteraction(permissions.BasePermission):
    """Permission to check if user can view a specific interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        if not request.user.is_authenticated:
            return False

        puppets = request.user.get_puppeted_characters()
        if not puppets:
            return False

        character = puppets[0]
        try:
            roster_entry = character.roster_entry
        except AttributeError:
            return False

        return can_view_interaction(
            obj,
            roster_entry,
            is_staff=request.user.is_staff,
        )


class IsInteractionWriter(permissions.BasePermission):
    """Permission to check if user is the interaction writer or staff."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        if request.user.is_staff:
            return True

        puppets = request.user.get_puppeted_characters()
        if not puppets:
            return False

        character = puppets[0]
        try:
            roster_entry = character.roster_entry
        except AttributeError:
            return False

        return obj.roster_entry_id == roster_entry.pk

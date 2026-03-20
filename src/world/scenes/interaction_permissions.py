from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from evennia_extensions.models import PlayerData
from world.character_sheets.models import Guise
from world.roster.models import RosterEntry
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.models import Interaction, InteractionAudience


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


def get_account_guises(request: Request) -> list[int]:
    """Get all guise IDs for characters owned by the requesting account."""
    roster_entries = get_account_roster_entries(request)
    if not roster_entries:
        return []
    character_ids = [re.character_id for re in roster_entries]
    return list(Guise.objects.filter(character_id__in=character_ids).values_list("id", flat=True))


def _is_audience_or_writer(
    obj: Interaction,
    guise_ids: list[int],
) -> bool:
    """Check if any of the guise IDs match the interaction's writer or audience."""
    if not guise_ids:
        return False
    is_writer = obj.persona.guise_id in guise_ids
    is_audience = InteractionAudience.objects.filter(
        interaction=obj,
        guise_id__in=guise_ids,
    ).exists()
    return is_writer or is_audience


def _requires_audience_check(obj: Interaction) -> bool:
    """Return True if the interaction is restricted to audience/writer only."""
    if obj.visibility == InteractionVisibility.VERY_PRIVATE:
        return True
    scene = obj.scene
    if scene and scene.privacy_mode == ScenePrivacyMode.PRIVATE:
        return True
    if obj.mode == InteractionMode.WHISPER:
        return True
    return False


class CanViewInteraction(permissions.BasePermission):
    """Permission to check if user can view a specific interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        user = request.user
        guise_ids = get_account_guises(request)

        # Very private: only audience/writer guises, never staff
        if obj.visibility == InteractionVisibility.VERY_PRIVATE:
            return _is_audience_or_writer(obj, guise_ids)

        # Staff sees everything except very_private
        if user.is_staff:
            return True

        # Public scene: visible to all
        scene = obj.scene
        if scene and scene.privacy_mode == ScenePrivacyMode.PUBLIC:
            return True

        # Private scene, whisper, or other restricted modes
        if _requires_audience_check(obj):
            return _is_audience_or_writer(obj, guise_ids)

        # Default: public (pose/emit/say/shout/action without a scene)
        return True


class IsInteractionWriter(permissions.BasePermission):
    """Only the writer can modify/delete their interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        guise_ids = get_account_guises(request)
        return obj.persona.guise_id in guise_ids

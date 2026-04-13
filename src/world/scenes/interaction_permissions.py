from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from evennia_extensions.models import PlayerData
from world.roster.models import RosterEntry
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.models import Interaction, Persona
from world.scenes.place_models import InteractionReceiver


def get_account_roster_entries(request: Request) -> list[RosterEntry]:
    """Return all roster entries belonging to the authenticated user's account.

    Path: Account -> PlayerData -> RosterTenure (current) -> RosterEntry
    Results are cached per-request to avoid redundant queries.
    """
    _cache_attr = "_cached_roster_entries"
    cached = getattr(request, _cache_attr, None)
    if cached is not None:
        return cached

    user = request.user
    if not user.is_authenticated:
        setattr(request, _cache_attr, [])
        return []
    try:
        player_data = PlayerData.objects.get(account=user)
    except PlayerData.DoesNotExist:
        setattr(request, _cache_attr, [])
        return []
    entries = list(
        RosterEntry.objects.filter(
            tenures__player_data=player_data,
            tenures__end_date__isnull=True,
        )
    )
    setattr(request, _cache_attr, entries)
    return entries


def get_account_personas(request: Request) -> list[int]:
    """Get all persona IDs for characters owned by the requesting account."""
    roster_entries = get_account_roster_entries(request)
    if not roster_entries:
        return []
    character_ids = [re.character_id for re in roster_entries]
    return list(
        Persona.objects.filter(character_sheet_id__in=character_ids).values_list("id", flat=True)
    )


def _is_receiver_or_writer(
    obj: Interaction,
    persona_ids: list[int],
) -> bool:
    """Check if any of the persona IDs match the interaction's writer or receivers."""
    if not persona_ids:
        return False
    is_writer = obj.persona_id in persona_ids
    is_receiver = InteractionReceiver.objects.filter(
        interaction=obj,
        persona_id__in=persona_ids,
    ).exists()
    return is_writer or is_receiver


def _requires_receiver_check(obj: Interaction) -> bool:
    """Return True if the interaction is restricted to receivers/writer only."""
    if obj.visibility == InteractionVisibility.VERY_PRIVATE:
        return True
    if obj.place_id is not None:
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
        persona_ids = get_account_personas(request)

        # Very private: only receivers/writer personas, never staff
        if obj.visibility == InteractionVisibility.VERY_PRIVATE:
            return _is_receiver_or_writer(obj, persona_ids)

        # Staff sees everything except very_private
        if user.is_staff:
            return True

        # Public scene: visible to all
        scene = obj.scene
        if scene and scene.privacy_mode == ScenePrivacyMode.PUBLIC:
            return True

        # Place-scoped, private scene, whisper, or other restricted modes
        if _requires_receiver_check(obj):
            return _is_receiver_or_writer(obj, persona_ids)

        # Default: public (pose/emit/say/shout/action without a scene)
        return True


class IsInteractionWriter(permissions.BasePermission):
    """Only the writer can modify/delete their interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        persona_ids = get_account_personas(request)
        return obj.persona_id in persona_ids

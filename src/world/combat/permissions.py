"""Permission classes for combat API endpoints."""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.combat.constants import ParticipantStatus
from world.combat.models import CombatEncounter, CombatParticipant
from world.roster.models import RosterEntry


class IsEncounterGMOrStaff(BasePermission):
    """Allow access to GMs of the encounter's scene or staff.

    Uses Scene.is_gm() which reads from participations_cached — no query
    if the scene is already in the identity map.
    """

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: CombatEncounter,
    ) -> bool:
        if request.user.is_staff:
            return True
        if not obj.scene:
            return False
        return obj.scene.is_gm(request.user)


class IsEncounterParticipant(BasePermission):
    """Allow authenticated users who have an active CombatParticipant.

    Uses the encounter's participants_cached when available (prefetched
    by _base_queryset) to avoid a separate query.
    """

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: CombatEncounter,
    ) -> bool:
        if request.user.is_staff:
            return True
        user = cast(AccountDB, request.user)
        character_ids = set(
            RosterEntry.objects.for_account(user).character_ids(),
        )
        try:
            participants = obj.participants_cached
            return any(p.character_sheet.character_id in character_ids for p in participants)
        except AttributeError:
            # Fallback if encounter wasn't loaded via _base_queryset
            return CombatParticipant.objects.filter(
                encounter=obj,
                character_sheet__character_id__in=character_ids,
                status=ParticipantStatus.ACTIVE,
            ).exists()


class IsInEncounterRoom(BasePermission):
    """Allow any PC currently in the encounter's scene location.

    Uses Scene.has_character_present() which reads the room's contents
    cache — no DB query for location presence.
    """

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: CombatEncounter,
    ) -> bool:
        if request.user.is_staff:
            return True
        if not obj.scene:
            return False
        user = cast(AccountDB, request.user)
        character_ids = set(
            RosterEntry.objects.for_account(user).character_ids(),
        )
        return obj.scene.has_character_present(character_ids)

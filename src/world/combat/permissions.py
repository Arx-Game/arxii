"""Permission classes for combat API endpoints."""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.combat.constants import ParticipantStatus
from world.combat.models import CombatEncounter, CombatParticipant
from world.roster.models import RosterEntry
from world.scenes.models import Scene


class IsEncounterGMOrStaff(BasePermission):
    """Allow access to GMs of the encounter's scene or staff."""

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: CombatEncounter,
    ) -> bool:
        if request.user.is_staff:
            return True
        if not obj.scene_id:
            return False
        return Scene.objects.filter(
            pk=obj.scene_id,
            participations__account=request.user,
            participations__is_gm=True,
        ).exists()


class IsEncounterParticipant(BasePermission):
    """Allow authenticated users who have a CombatParticipant in this encounter.

    Stashes the resolved participant on the view as `_combat_participant`
    so the action method can reuse it without a second query.
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
        active_entries = RosterEntry.objects.for_account(user)
        character_ids = active_entries.values_list("character_id", flat=True)
        participant = CombatParticipant.objects.filter(
            encounter=obj,
            character_sheet__character_id__in=character_ids,
            status=ParticipantStatus.ACTIVE,
        ).first()
        if participant:
            if view is not None:
                view.combat_participant = participant
            return True
        return False


class IsInEncounterRoom(BasePermission):
    """Allow any PC currently in the encounter's scene location.

    Used for the join endpoint -- any character physically present
    in the room where combat is happening can join.
    """

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: CombatEncounter,
    ) -> bool:
        if request.user.is_staff:
            return True
        if not obj.scene_id:
            return False
        try:
            scene = Scene.objects.get(pk=obj.scene_id)
        except Scene.DoesNotExist:
            return False
        if not scene.location_id:
            return False
        user = cast(AccountDB, request.user)
        active_entries = RosterEntry.objects.for_account(user)
        character_ids = active_entries.values_list("character_id", flat=True)
        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        return ObjectDB.objects.filter(
            pk__in=character_ids,
            db_location_id=scene.location_id,
        ).exists()

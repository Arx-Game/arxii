"""Permission classes for combat API endpoints."""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.combat.models import CombatEncounter
from world.roster.models import RosterEntry


def _viewer_character_ids(request: Request, view: APIView) -> set[int]:
    """Return the request user's played character_sheet ids.

    Prefers ``view._viewer_character_ids(request)`` when the view exposes
    it (``CombatEncounterViewSet`` does — it caches the set on the
    request object so permission checks and view body share the same
    roster query). Falls back to a direct query for any caller wired up
    with these permissions but lacking the helper.
    """
    helper = getattr(view, "_viewer_character_ids", None)  # noqa: GETATTR_LITERAL
    if helper is not None:
        return helper(request)
    if not request.user.is_authenticated:
        return set()
    user = cast(AccountDB, request.user)
    return set(RosterEntry.objects.for_account(user).character_ids())


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
    by _base_queryset) to avoid a separate query. Routes the roster
    lookup through the view's per-request cache when available so the
    permission check and view body share a single roster query.
    """

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: CombatEncounter,
    ) -> bool:
        if request.user.is_staff:
            return True
        character_ids = _viewer_character_ids(request, view)
        return any(p.character_sheet.character_id in character_ids for p in obj.participants_cached)


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
        character_ids = _viewer_character_ids(request, view)
        return obj.scene.has_character_present(character_ids)

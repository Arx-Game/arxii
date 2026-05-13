"""Permission classes for combat API endpoints."""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.combat.models import CombatEncounter


def _viewer_character_ids(request: Request, view: APIView) -> set[int]:
    """Return the request user's played character_sheet ids.

    Always routes through ``view._viewer_character_ids(request)`` —
    these permissions are wired to ``CombatEncounterViewSet`` (in
    production) and to a stub view in ``test_permissions`` (in tests).
    The view caches the set on ``request._combat_viewer_character_ids``
    so the permission check and view body share a single roster query.
    """
    return view._viewer_character_ids(request)  # noqa: SLF001 — known cooperator


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

    **No staff bypass.** The endpoints gated by this permission
    (``declare``, ``ready``, ``my_action``, ``flee``, ``upgrade_combo``,
    ``revert_combo``) operate on the caller's own participant row. Staff
    do not own a participant by virtue of being staff — they must be
    added as a participant first (e.g., via the ``add_participant`` GM
    action) before they can act. Granting a staff bypass here paints an
    inconsistent picture: the permission check passes, but the view
    body's ``_get_participant`` returns None and the request 403s on
    "Not a participant" — confusing and pointless.
    """

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: CombatEncounter,
    ) -> bool:
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

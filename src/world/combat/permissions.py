"""Permission classes for combat API endpoints."""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.combat.models import CombatEncounter
from world.roster.models import RosterEntry


def _viewer_character_ids(request: Request, view: APIView | None) -> set[int]:
    """Return the request user's played character_sheet ids.

    In production these permissions are only wired to
    ``CombatEncounterViewSet``, which exposes ``_viewer_character_ids``
    and caches the set on the request object so permission checks and
    view body share a single roster query — we prefer that path.

    When the helper isn't available (notably in ``test_permissions``
    which pass ``view=None`` to drive ``has_object_permission`` in
    isolation), fall back to a direct query. The fallback is functionally
    equivalent; it just doesn't share state with a view that isn't there.
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

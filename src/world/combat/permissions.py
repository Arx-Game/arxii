"""Permission classes for combat API endpoints."""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.combat.models import CombatEncounter

_CREATE_ACTION = "create"
# Actions with no CombatEncounter object yet, gated by the *named scene's*
# GM/owner-or-staff standing rather than has_object_permission (#3068 widens
# this from {"create"} — DuelChallengeViewSet.propose_lethal_duel reuses this
# same class/gate for the same reason CombatEncounterViewSet.create does: a
# GM proposing a lethal duel has no encounter to check permissions against
# yet either).
_SCENE_GATED_ACTIONS = frozenset({_CREATE_ACTION, "propose_lethal_duel"})


def can_create_encounter_for_scene(account: object, scene: object) -> bool:
    """True iff *account* may create a CombatEncounter anchored to *scene*.

    Staff, the scene's GM, or the scene's co-owner — mirrors
    ``SceneSerializer.get_viewer_can_gm`` exactly (world/scenes/serializers.py:272-277) so
    the web "Start encounter" button's visibility and this create gate never diverge, and
    so telnet `encounter create` (#3388) accepts precisely the accounts the web button
    would show. Shared by ``IsEncounterGMOrStaff.has_permission``'s SCENE_GATED_ACTIONS
    branch (web) and ``actions.definitions.gm_combat._actor_may_start_encounter`` (telnet)
    — do not re-derive this OR chain a third time.
    """
    return bool(account.is_staff or scene.is_gm(account) or scene.is_owner(account))


def can_view_encounter_effects(user: object, encounter: CombatEncounter) -> bool:
    """Return True iff ``user`` may view an encounter's effect details.

    Staff, the encounter's scene GM, and encounter participants (PCs in the
    fight) see effects; everyone else sees none. Stricter than scene
    visibility by design — effect/power-ledger detail is more sensitive than
    spectating the scene.
    """

    # Every Django user-like (User AND AnonymousUser) defines is_authenticated;
    # a non-user object failing loudly here is correct (#2386 tranche 3).
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if encounter.scene.is_gm(user):
        return True
    character_ids = user.played_character_sheet_ids
    return any(
        p.character_sheet.character_id in character_ids for p in encounter.participants.all()
    )


def _viewer_character_ids(request: Request, _view: APIView) -> frozenset[int]:
    """Return the request user's played character_sheet ids.

    Reads ``request.user.played_character_sheet_ids`` — a cached_property
    on the ``Account`` typeclass populated lazily and invalidated when
    any of the account's ``RosterTenure`` rows mutate (see
    ``RosterTenure.related_cache_fields``). The cache lives on the
    identity-mapped Account instance, so it persists across requests for
    the same user within the same Python process.

    For anonymous users or non-Account user models, ``AttributeError``
    bubbles up from the missing property and we return an empty set.
    """
    try:
        return request.user.played_character_sheet_ids
    except AttributeError:
        return frozenset()


class IsEncounterGMOrStaff(BasePermission):
    """Allow access to GMs of the encounter's scene or staff.

    Uses Scene.is_gm() which reads from participations_cached — no query
    if the scene is already in the identity map.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Gate ``create``/``propose_lethal_duel`` to the scene's GM/owner (or staff).

        Both actions have no object yet (a new CombatEncounter, or a new
        DuelChallenge with no encounter at all), so DRF never calls
        ``has_object_permission`` for them — every other action here is
        detail-routed (``get_object()`` runs first, then the object check
        below). Without this override, any authenticated user could POST an
        encounter — or a lethal-duel proposal — into a scene they don't GM.
        Not a behavior change for any other action: they still fall through
        to the unconditional ``True``.

        Staff-or-GM-or-owner mirrors the established "can this user do
        GM-ish things to this scene" predicate used elsewhere for scene
        write actions (``Scene.get_viewer_can_gm``,
        ``world.scenes.permissions.IsSceneGMOrOwnerOrStaff``) rather than
        the narrower is_gm-only check ``has_object_permission`` below uses
        for the existing round-control actions — the web "Start encounter"
        button reads ``scene.viewer_can_gm`` to decide whether to render at
        all, so the create gate must match that signal exactly or a scene
        owner who isn't separately flagged ``is_gm`` would see a button the
        server then 403s.
        """
        if view.action not in _SCENE_GATED_ACTIONS:
            return True
        if request.user.is_staff:
            return True
        scene_id = request.data.get("scene")
        if not scene_id:
            return False
        from world.scenes.models import Scene  # noqa: PLC0415

        scene = Scene.objects.filter(pk=scene_id).first()
        if scene is None:
            return False
        return can_create_encounter_for_scene(request.user, scene)

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: CombatEncounter,
    ) -> bool:
        if request.user.is_staff:
            return True
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
        character_ids = _viewer_character_ids(request, view)
        return obj.scene.has_character_present(character_ids)

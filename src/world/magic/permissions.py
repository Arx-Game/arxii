"""Permission classes for the magic API."""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from world.magic.constants import RitualExecutionKind
from world.magic.models import AnimaRitualPerformance, Ritual, Thread
from world.magic.models.sessions import RitualSession
from world.roster.models import RosterEntry


def _active_sheet_ids_for_user(user: object) -> set[int]:
    """Return the set of CharacterSheet PKs the user currently plays.

    Walks the active RosterTenure chain:
    AccountDB → PlayerData → active RosterTenure (end_date__isnull=True)
    → RosterEntry → CharacterSheet.
    """
    account = cast(AccountDB, user)
    return set(RosterEntry.objects.for_account(account).character_ids())


def known_ritual_ids_for_request(request: Request) -> set[int]:
    """Return the ids of the anima rituals the character the request acts as knows (#5280).

    The anima ritual is in character and belongs to the character who knows it, so what a
    player may see or edit of it is read through ``CharacterRitualKnowledge`` on the character
    she is browsing as (``character_for_request``), never through the account that authored it
    and never through every character the account plays. No selected character knows none,
    and neither does a selected character the player no longer plays (a tenure that ended
    leaves the selection behind): this is the tenure permission boundary, so the account's
    current tenures are read here on purpose.
    """
    from world.magic.services.anima import character_scene_action_rituals  # noqa: PLC0415
    from world.roster.services.selection import character_for_request  # noqa: PLC0415

    character = character_for_request(request, entry_id=None)
    if character is None or character.pk not in _active_sheet_ids_for_user(request.user):
        return set()
    return set(character_scene_action_rituals(character.pk).values_list("pk", flat=True))


def can_edit_ritual(user: object, ritual: Ritual, *, known_ritual_ids: set[int]) -> bool:
    """Whether ``user`` may edit ``ritual``; ``known_ritual_ids`` is the acting character's.

    Staff may edit any ritual. A staff-authored ritual (no author) is staff-only. A player's
    anima ritual (SCENE_ACTION) is edited from the character who knows it. Any other
    player-authored ritual is edited by the account that authored it.
    """
    if cast(AccountDB, user).is_staff:
        return True
    author_id = ritual.author_account_id
    if author_id is None:
        return False
    if ritual.execution_kind == RitualExecutionKind.SCENE_ACTION:
        return ritual.pk in known_ritual_ids
    return author_id == cast(AccountDB, user).pk


class IsRitualAuthorOrStaff(BasePermission):
    """Allow write access only to the Ritual's author or staff.

    Safe methods (GET, HEAD, OPTIONS) are always allowed.
    Mutation (PATCH, PUT, DELETE) follows ``can_edit_ritual``:
    - Staff accounts (is_staff=True).
    - For a player's anima ritual (SCENE_ACTION with an author): a requester acting as the
      character who knows it (#5280). The ritual is in character and belongs to the
      character, so authorship alone does not let a player edit it from another character,
      even one on the same account, and a player who takes over the character can.
    - For any other player-authored ritual: the account that authored it
      (ritual.author_account == request.user).

    Staff-authored rituals (author_account=NULL) cannot be mutated by non-staff.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return can_edit_ritual(
            request.user, obj, known_ritual_ids=known_ritual_ids_for_request(request)
        )


class IsThreadOwner(BasePermission):
    """Allow access only if the Thread's owner CharacterSheet belongs to ``request.user``.

    Staff always pass. Ownership is resolved through the account's active
    roster tenures (the same pattern used by the combat views), not through
    ``ObjectDB.db_account`` — Evennia characters are not always directly
    linked to an account FK in Arx II; roster tenures carry the relationship.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Thread) -> bool:
        if request.user.is_staff:
            return True
        user = cast(AccountDB, request.user)
        owned_sheet_ids = RosterEntry.objects.for_account(user).character_ids()
        return obj.owner_id in set(owned_sheet_ids)


# =============================================================================
# Ritual Session permission classes (Covenants Slice B §4.12)
# =============================================================================


class IsRitualSessionParticipantOrInitiator(BasePermission):
    """GET detail: allow if the user is the initiator OR an invited participant.

    Walks the active RosterTenure chain to resolve the user's character sheets,
    then checks whether any of those sheets appear as initiator or participant.
    Staff always pass.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: RitualSession) -> bool:
        if request.user.is_staff:
            return True
        my_sheet_ids = _active_sheet_ids_for_user(request.user)
        if obj.initiator_id in my_sheet_ids:
            return True
        return obj.participants.filter(character_sheet_id__in=my_sheet_ids).exists()


class IsRitualSessionInitiator(BasePermission):
    """fire / cancel (DELETE): only the initiator's currently-playing user may act.

    Staff always pass.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: RitualSession) -> bool:
        if request.user.is_staff:
            return True
        my_sheet_ids = _active_sheet_ids_for_user(request.user)
        return obj.initiator_id in my_sheet_ids


class CanPrepareCharacterText(BasePermission):
    """Staff, or the character's table GM (#4101 decision 9)."""

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        from world.magic.services.prepared_text import may_prepare_text_for  # noqa: PLC0415

        return may_prepare_text_for(request.user, obj.character_sheet)


class IsInvitedParticipant(BasePermission):
    """accept / decline: the action must target a participant row owned by the user.

    This permission checks the session-level object (RitualSession). The view
    then separately resolves the requesting user's participant row. If the user
    is not a participant (not the initiator and no participant row), they are denied.
    Staff always pass.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: RitualSession) -> bool:
        if request.user.is_staff:
            return True
        my_sheet_ids = _active_sheet_ids_for_user(request.user)
        # User must be a participant (not the initiator) to accept/decline.
        return obj.participants.filter(character_sheet_id__in=my_sheet_ids).exists()


class IsStaffOrReadOnly(BasePermission):
    """Any authenticated user may read; only staff may write (#4197).

    The flat Facet vocabulary: every player's pickers read it, staff grow it.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user.is_staff)


#: The router's own create/update/delete actions. A viewset's custom ``@action`` writes
#: (an aura's glimpse picks, say) are not among them and keep their own gates.
BASE_WRITE_ACTIONS = frozenset({"create", "update", "partial_update", "destroy"})


class IsStaffForBaseWrites(BasePermission):
    """Any authenticated user may read; only staff may use the raw create, update and delete.

    For a character-data viewset whose rows the game writes through services (a gift is
    gained through ``grant_gift_to_character``, anima through its rituals), so a player
    who could write the row directly would skip every rule (#4898). Custom ``@action``
    routes are untouched.
    """

    def has_permission(self, request: Request, view: GenericViewSet) -> bool:
        if not request.user.is_authenticated:
            return False
        if view.action in BASE_WRITE_ACTIONS:
            return bool(request.user.is_staff)
        return True


class PlaysTheRitualPartner(BasePermission):
    """Answering an anima ritual (#5280): only the player of the character it reached for.

    "Plays" is the active tenure, as the other magic permissions read it. Staff get no
    exception: the answer is the partner's own.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AnimaRitualPerformance
    ) -> bool:
        return obj.target_character_id in _active_sheet_ids_for_user(request.user)


class CanUndoResonanceGrant(BasePermission):
    """Undoing a resonance reward (#5327): staff, or the GM of the scene it happened in.

    ``Scene.is_gm`` decides, never ``is_owner``: every player present when a scene starts is a
    co-owner, and an owner who is not its GM must not undo rewards. The rule itself lives in
    ``services.undo.may_undo_grant``, which the service checks again.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        from world.magic.services.undo import may_undo_grant  # noqa: PLC0415

        return may_undo_grant(cast(AccountDB, request.user), obj)

"""Permission classes for the magic API."""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.magic.models import Thread
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


class IsRitualAuthorOrStaff(BasePermission):
    """Allow write access only to the Ritual's author or staff.

    Safe methods (GET, HEAD, OPTIONS) are always allowed.
    Mutation (PATCH, PUT, DELETE) is restricted to:
    - Staff accounts (is_staff=True).
    - The account that authored the ritual (ritual.author_account == request.user).

    Staff-authored rituals (author_account=NULL) cannot be mutated by non-staff.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_staff:
            return True
        author_id = getattr(obj, "author_account_id", None)  # noqa: GETATTR_LITERAL — duck-typed obj may not have the attr
        if author_id is None:
            return False  # staff-authored ritual — non-staff cannot mutate
        return author_id == request.user.id


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

"""Permission classes for the magic API."""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.magic.models import Thread
from world.roster.models import RosterEntry


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

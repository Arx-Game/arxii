"""Permission classes for the magic API."""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.magic.models import Thread
from world.roster.models import RosterEntry


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

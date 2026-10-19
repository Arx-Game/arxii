"""Shared API permission classes."""

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class IsCharacterOwner(permissions.BasePermission):
    """Validates the requesting account may play the character identified by
    'character_id' in the URL kwargs.

    The same rule as puppeting (#4418): the account's playable entries
    (``Account.cached_roster_entries``, ``RosterEntry.objects.playable_by``), so a
    Guide borrowing a lent NPC may act as it from the web, and its owner may not
    while it is lent. Before this a lent NPC's every web dispatch was a 403.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.user.is_staff:
            return True
        character_id = view.kwargs.get("character_id")
        if character_id is None:
            return False
        try:
            entries = request.user.cached_roster_entries
        except AttributeError:
            return False
        entry = next((e for e in entries if e.character_sheet_id == int(character_id)), None)
        if entry is None:
            return False
        tenure = entry.current_tenure
        if tenure is not None and tenure.player_data.account_id == request.user.pk:
            # The account's own character: only once its tenure has begun.
            return tenure.start_date is not None
        # Someone else holds it, so an ACTIVE loan to this account put it in the list.
        return True

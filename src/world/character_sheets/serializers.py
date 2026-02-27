"""
Serializers for the character sheets API.
"""

from rest_framework import serializers
from rest_framework.request import Request

from world.roster.models import RosterEntry


class CharacterSheetSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for character sheet data, looked up via RosterEntry.

    Returns a `can_edit` boolean indicating whether the requesting user
    is the original creator (player_number=1) or a staff member.
    """

    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = RosterEntry
        fields = ["id", "can_edit"]

    def get_can_edit(self, obj: RosterEntry) -> bool:
        """
        True if the requesting user is the original account (first tenure) or staff.

        The original account is the player_data.account from the tenure with
        player_number=1. A current player who picked up a roster character
        (player_number > 1) does NOT get edit rights.

        Uses prefetched tenures from the viewset queryset to avoid extra queries.
        """
        request: Request | None = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return False

        if request.user.is_staff:
            return True

        # Walk prefetched tenures to avoid an extra query
        original_tenure = next(
            (t for t in obj.tenures.all() if t.player_number == 1),
            None,
        )
        if original_tenure is None:
            return False

        return original_tenure.player_data.account == request.user

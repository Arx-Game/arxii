"""
Roster and RosterEntry serializers for the roster system.
"""

from rest_framework import serializers

from world.roster.models import Roster, RosterEntry
from world.roster.serializers.characters import CharacterSerializer
from world.roster.serializers.media import TenureMediaSerializer
from world.roster.serializers.tenures import RosterTenureSerializer


class RosterEntrySerializer(serializers.ModelSerializer):
    """Serialize roster entry data with nested character info."""

    character = CharacterSerializer(read_only=True)
    profile_picture = TenureMediaSerializer(read_only=True)
    tenures = RosterTenureSerializer(many=True, read_only=True)
    can_apply = serializers.SerializerMethodField()
    fullname = serializers.SerializerMethodField()
    quote = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    class Meta:
        model = RosterEntry
        fields = (
            "id",
            "character",
            "profile_picture",
            "tenures",
            "can_apply",
            "fullname",
            "quote",
            "description",
        )
        read_only_fields = fields

    def get_can_apply(self, obj):
        """Return whether the requester may apply to play this character."""

        request = self.context.get("request")
        return bool(
            request and request.user.is_authenticated and obj.accepts_applications,
        )

    def get_fullname(self, obj):
        """Character's full long name."""
        try:
            item_data = obj.character.item_data
            return getattr(item_data, "longname", "") or ""
        except AttributeError:
            return ""

    def get_quote(self, obj):
        """Character's quote."""
        try:
            item_data = obj.character.item_data
            return getattr(item_data, "quote", "") or ""
        except AttributeError:
            return ""

    def get_description(self, obj):
        """Character's current description."""
        try:
            item_data = obj.character.item_data
            if hasattr(item_data, "get_display_description"):
                return item_data.get_display_description() or ""
            return ""
        except AttributeError:
            return ""


class MyRosterEntrySerializer(serializers.ModelSerializer):
    """Serialize a summary of a roster entry for account menus."""

    name = serializers.CharField(source="character.db_key")

    class Meta:
        model = RosterEntry
        fields = ("id", "name")
        read_only_fields = fields


class RosterEntryListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing available roster entries to apply for.
    Automatically filters based on player permissions and eligibility.
    """

    character_name = serializers.CharField(source="character.db_key", read_only=True)
    character_id = serializers.IntegerField(source="character.id", read_only=True)
    roster_name = serializers.CharField(source="roster.name", read_only=True)
    roster_description = serializers.CharField(
        source="roster.description",
        read_only=True,
    )
    is_available = serializers.SerializerMethodField()
    trust_evaluation = serializers.SerializerMethodField()

    class Meta:
        model = RosterEntry
        fields = [
            "id",
            "character_id",
            "character_name",
            "roster_name",
            "roster_description",
            "is_available",
            "trust_evaluation",
            "joined_roster",
        ]

    def get_is_available(self, obj):
        """Check if character is available for application."""
        return obj.accepts_applications

    def get_trust_evaluation(self, obj):
        """Get trust evaluation for this player/character combination."""
        request = self.context.get("request")
        if not request or not hasattr(request.user, "player_data"):
            return

        # TODO: Implement trust evaluation when trust system is ready
        # return TrustEvaluator.evaluate_player_for_character(
        #     request.user.player_data, obj.character
        # )
        return


class RosterListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing rosters with character counts.
    """

    available_count = serializers.SerializerMethodField()

    class Meta:
        model = Roster
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "allow_applications",
            "available_count",
        ]

    def get_available_count(self, obj):
        """
        Get count of available characters in this roster for the requesting player.
        """
        request = self.context.get("request")
        if not request or not hasattr(request.user, "player_data"):
            return 0

        # TODO: Filter based on player trust when trust system is implemented
        # For now, return count of all characters in active roster
        # This is a placeholder until trust system is implemented
        if not obj.is_active or not obj.allow_applications:
            return 0
        return obj.entries.exclude(tenures__end_date__isnull=True).count()

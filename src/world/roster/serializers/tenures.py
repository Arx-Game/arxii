"""
Tenure-related serializers for the roster system.
"""

from rest_framework import serializers

from world.roster.models import RosterTenure
from world.roster.serializers.media import TenureMediaSerializer


class RosterTenureSerializer(serializers.ModelSerializer):
    """Serialize roster tenure information with nested media."""

    media = TenureMediaSerializer(many=True, read_only=True)

    class Meta:
        model = RosterTenure
        fields = (
            "id",
            "player_number",
            "start_date",
            "end_date",
            "applied_date",
            "approved_date",
            "approved_by",
            "tenure_notes",
            "photo_folder",
            "media",
        )
        read_only_fields = fields


class RosterTenureLookupSerializer(serializers.ModelSerializer):
    """Lightweight serializer for searching tenures."""

    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = RosterTenure
        fields = ["id", "display_name"]
        read_only_fields = fields

"""
Tenure-related serializers for the roster system.
"""

from typing import ClassVar

from rest_framework import serializers

from world.roster.models import RosterTenure


class RosterTenureSerializer(serializers.ModelSerializer):
    """Serialize roster tenure information.

    No nested media (#4151): this is served to anyone by the roster list, and art is
    shown only to accounts. A character's pictures come from its Gallery endpoint.
    """

    class Meta:
        model = RosterTenure
        fields: ClassVar[tuple[str, ...]] = (
            "id",
            "player_number",
            "start_date",
            "end_date",
            "applied_date",
            "approved_date",
            "approved_by",
            "tenure_notes",
            "photo_folder",
        )
        read_only_fields: ClassVar[tuple[str, ...]] = fields


class RosterTenureLookupSerializer(serializers.ModelSerializer):
    """Lightweight serializer for searching tenures."""

    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = RosterTenure
        fields: ClassVar[list[str]] = ["id", "display_name"]
        read_only_fields: ClassVar[list[str]] = fields

"""
Media and gallery serializers for the roster system.
"""

from rest_framework import serializers

from evennia_extensions.models import Artist, PlayerMedia
from world.roster.models import TenureMedia


class ArtistSerializer(serializers.ModelSerializer):
    """Serialize artist information."""

    class Meta:
        model = Artist
        fields = (
            "id",
            "name",
            "description",
            "commission_notes",
            "accepting_commissions",
        )
        read_only_fields = fields


class PlayerMediaSerializer(serializers.ModelSerializer):
    """Serialize media uploaded by a player."""

    created_by = serializers.SerializerMethodField()

    def get_created_by(self, obj: PlayerMedia):
        """Return serialized artist information if present."""
        artist = obj.created_by
        if not artist:
            return None
        return ArtistSerializer(artist).data

    class Meta:
        model = PlayerMedia
        fields = (
            "id",
            "cloudinary_public_id",
            "cloudinary_url",
            "media_type",
            "title",
            "description",
            "created_by",
            "uploaded_date",
            "updated_date",
        )
        read_only_fields = fields


class TenureMediaSerializer(serializers.ModelSerializer):
    """Serialize media associated with a roster tenure."""

    media = PlayerMediaSerializer(read_only=True)

    class Meta:
        model = TenureMedia
        fields = ("id", "media", "sort_order", "is_public")
        read_only_fields = ("id", "media")

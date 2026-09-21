"""DRF serializers for the relationships system (#3957)."""

from rest_framework import serializers

from world.relationships.models import RelationshipCapstone, RelationshipCondition


class RelationshipConditionSerializer(serializers.ModelSerializer):
    """Serializer for RelationshipCondition lookup table."""

    class Meta:
        model = RelationshipCondition
        fields = ["id", "name", "description", "display_order"]
        read_only_fields = fields


class RelationshipCapstoneSerializer(serializers.ModelSerializer):
    """Serializer for relationship capstone events (#3957)."""

    title = serializers.CharField(read_only=True)

    class Meta:
        model = RelationshipCapstone
        fields = [
            "id",
            "relationship",
            "journal_entry",
            "title",
            "tier_claimed",
            "xp_spent",
            "is_ritual_capstone",
            "created_at",
        ]
        read_only_fields = fields

"""
Relationships System Serializers

DRF serializers for character relationship models.
"""

from rest_framework import serializers

from world.relationships.models import CharacterRelationship, RelationshipCondition


class RelationshipConditionSerializer(serializers.ModelSerializer):
    """Serializer for RelationshipCondition lookup table."""

    gates_modifiers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = RelationshipCondition
        fields = ["id", "name", "description", "display_order", "gates_modifiers"]


class RelationshipConditionListSerializer(serializers.ModelSerializer):
    """Lighter serializer for condition lists in relationships."""

    class Meta:
        model = RelationshipCondition
        fields = ["id", "name"]


class CharacterRelationshipSerializer(serializers.ModelSerializer):
    """Serializer for CharacterRelationship.

    Uses CharacterSheet FKs. The source/target PKs are ObjectDB PKs since
    CharacterSheet uses character (ObjectDB) as its primary key.
    """

    # CharacterSheet.character is the ObjectDB FK (and PK), so we access db_key through it
    source_name = serializers.CharField(source="source.character.db_key", read_only=True)
    target_name = serializers.CharField(source="target.character.db_key", read_only=True)
    conditions = RelationshipConditionListSerializer(many=True, read_only=True)

    class Meta:
        model = CharacterRelationship
        fields = [
            "id",
            "source",
            "source_name",
            "target",
            "target_name",
            "reputation",
            "conditions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

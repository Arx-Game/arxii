"""
Mechanics System Serializers

DRF serializers for game mechanics models.
"""

from rest_framework import serializers

from world.mechanics.models import (
    CharacterModifier,
    ModifierCategory,
    ModifierSource,
    ModifierType,
)


class ModifierCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ModifierCategory
        fields = ["id", "name", "description", "display_order"]


class ModifierTypeSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ModifierType
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "description",
            "display_order",
            "is_active",
        ]


class ModifierTypeListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views."""

    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ModifierType
        fields = ["id", "name", "category", "category_name", "display_order", "is_active"]


class ModifierSourceSerializer(serializers.ModelSerializer):
    """Serializer for ModifierSource."""

    source_type = serializers.SerializerMethodField()
    source_display = serializers.CharField(read_only=True)

    class Meta:
        model = ModifierSource
        fields = [
            "id",
            "source_type",
            "source_display",
            "distinction_effect",
            "character_distinction",
            "condition_instance",
        ]
        read_only_fields = ["source_display"]

    def get_source_type(self, obj: ModifierSource) -> str:
        """Return a string indicating the source type."""
        if obj.distinction_effect_id or obj.character_distinction_id:
            return "distinction"
        if obj.condition_instance_id:
            return "condition"
        return "unknown"


class ModifierSourceListSerializer(serializers.ModelSerializer):
    """Lighter serializer for source in list views."""

    source_type = serializers.SerializerMethodField()
    source_display = serializers.CharField(read_only=True)

    class Meta:
        model = ModifierSource
        fields = ["id", "source_type", "source_display"]

    def get_source_type(self, obj: ModifierSource) -> str:
        if obj.distinction_effect_id or obj.character_distinction_id:
            return "distinction"
        if obj.condition_instance_id:
            return "condition"
        return "unknown"


class CharacterModifierSerializer(serializers.ModelSerializer):
    """Serializer for CharacterModifier."""

    modifier_type_name = serializers.CharField(source="modifier_type.name", read_only=True)
    category_name = serializers.CharField(source="modifier_type.category.name", read_only=True)
    character_name = serializers.CharField(source="character.character.db_key", read_only=True)
    source = ModifierSourceListSerializer(read_only=True)

    class Meta:
        model = CharacterModifier
        fields = [
            "id",
            "character",
            "character_name",
            "modifier_type",
            "modifier_type_name",
            "category_name",
            "value",
            "source",
            "expires_at",
            "created_at",
        ]
        read_only_fields = ["created_at"]

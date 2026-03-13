"""
Mechanics System Serializers

DRF serializers for game mechanics models.
"""

from rest_framework import serializers

from world.mechanics.models import (
    CharacterModifier,
    ModifierCategory,
    ModifierSource,
    ModifierTarget,
)


class ModifierCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ModifierCategory
        fields = ["id", "name", "description", "display_order"]


class ModifierTargetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ModifierTarget
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "description",
            "display_order",
            "is_active",
        ]


class ModifierTargetListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views."""

    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ModifierTarget
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "description",
            "display_order",
            "is_active",
        ]


class ModifierSourceSerializer(serializers.ModelSerializer):
    """Serializer for ModifierSource."""

    # Use property from model instead of duplicating logic
    source_type = serializers.CharField(read_only=True)
    source_display = serializers.CharField(read_only=True)

    class Meta:
        model = ModifierSource
        fields = [
            "id",
            "source_type",
            "source_display",
            "distinction_effect",
            "character_distinction",
        ]
        read_only_fields = ["source_type", "source_display"]


class ModifierSourceListSerializer(serializers.ModelSerializer):
    """Lighter serializer for source in list views."""

    # Use property from model instead of duplicating logic
    source_type = serializers.CharField(read_only=True)
    source_display = serializers.CharField(read_only=True)

    class Meta:
        model = ModifierSource
        fields = ["id", "source_type", "source_display"]


class CharacterModifierSerializer(serializers.ModelSerializer):
    modifier_target_id = serializers.PrimaryKeyRelatedField(source="target", read_only=True)
    modifier_target_name = serializers.CharField(source="target.name", read_only=True)
    category_name = serializers.CharField(source="target.category.name", read_only=True)
    character_name = serializers.CharField(source="character.character.db_key", read_only=True)
    source = ModifierSourceListSerializer(read_only=True)

    class Meta:
        model = CharacterModifier
        fields = [
            "id",
            "character",
            "character_name",
            "modifier_target_id",
            "modifier_target_name",
            "category_name",
            "value",
            "source",
            "expires_at",
            "created_at",
        ]
        read_only_fields = ["created_at"]

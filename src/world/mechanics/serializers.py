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
            "opposite",
            "resonance_affinity",
        ]


class ModifierTypeListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views."""

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
            "opposite",
            "resonance_affinity",
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
    """Serializer for CharacterModifier.

    modifier_type is derived from source.distinction_effect.target, so we use
    SerializerMethodField to safely access it through the property.
    """

    modifier_type_id = serializers.SerializerMethodField()
    modifier_type_name = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    character_name = serializers.CharField(source="character.character.db_key", read_only=True)
    source = ModifierSourceListSerializer(read_only=True)

    class Meta:
        model = CharacterModifier
        fields = [
            "id",
            "character",
            "character_name",
            "modifier_type_id",
            "modifier_type_name",
            "category_name",
            "value",
            "source",
            "expires_at",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_modifier_type_id(self, obj: CharacterModifier) -> int | None:
        mod_type = obj.modifier_type
        return mod_type.id if mod_type else None

    def get_modifier_type_name(self, obj: CharacterModifier) -> str | None:
        mod_type = obj.modifier_type
        return mod_type.name if mod_type else None

    def get_category_name(self, obj: CharacterModifier) -> str | None:
        mod_type = obj.modifier_type
        return mod_type.category.name if mod_type else None

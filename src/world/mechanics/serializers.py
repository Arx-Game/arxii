"""
Mechanics System Serializers

DRF serializers for game mechanics models.
"""

from rest_framework import serializers

from world.mechanics.models import CharacterModifier, ModifierCategory, ModifierType


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


class CharacterModifierSerializer(serializers.ModelSerializer):
    modifier_type_name = serializers.CharField(source="modifier_type.name", read_only=True)
    category_name = serializers.CharField(source="modifier_type.category.name", read_only=True)
    source_type = serializers.SerializerMethodField()
    source_id = serializers.SerializerMethodField()

    class Meta:
        model = CharacterModifier
        fields = [
            "id",
            "character",
            "modifier_type",
            "modifier_type_name",
            "category_name",
            "value",
            "source_type",
            "source_id",
            "expires_at",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_source_type(self, obj: CharacterModifier) -> str | None:
        if obj.source_distinction_id:
            return "distinction"
        if obj.source_condition_id:
            return "condition"
        return None

    def get_source_id(self, obj: CharacterModifier) -> int | None:
        return obj.source_distinction_id or obj.source_condition_id

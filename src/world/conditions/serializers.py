"""
Serializers for conditions system API.

Provides read-only serialization of condition data for the character sheet
conditions tab and other UI components.
"""

from rest_framework import serializers

from world.conditions.models import (
    CapabilityType,
    CheckType,
    ConditionCategory,
    ConditionInstance,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)

# =============================================================================
# Lookup Table Serializers
# =============================================================================


class ConditionCategorySerializer(serializers.ModelSerializer):
    """Serializer for condition categories."""

    class Meta:
        model = ConditionCategory
        fields = ["id", "name", "description", "is_negative", "display_order"]
        read_only_fields = fields


class CapabilityTypeSerializer(serializers.ModelSerializer):
    """Serializer for capability types."""

    class Meta:
        model = CapabilityType
        fields = ["id", "name", "description"]
        read_only_fields = fields


class CheckTypeSerializer(serializers.ModelSerializer):
    """Serializer for check types."""

    class Meta:
        model = CheckType
        fields = ["id", "name", "description"]
        read_only_fields = fields


class DamageTypeSerializer(serializers.ModelSerializer):
    """Serializer for damage types."""

    class Meta:
        model = DamageType
        fields = ["id", "name", "description", "color_hex", "icon"]
        read_only_fields = fields


# =============================================================================
# Template Serializers
# =============================================================================


class ConditionStageSerializer(serializers.ModelSerializer):
    """Serializer for condition stages."""

    class Meta:
        model = ConditionStage
        fields = [
            "id",
            "stage_order",
            "name",
            "description",
            "rounds_to_next",
            "severity_multiplier",
        ]
        read_only_fields = fields


class ConditionTemplateSerializer(serializers.ModelSerializer):
    """Serializer for condition template definitions."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    is_negative = serializers.BooleanField(source="category.is_negative", read_only=True)

    class Meta:
        model = ConditionTemplate
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "is_negative",
            "description",
            "player_description",
            "observer_description",
            "default_duration_type",
            "default_duration_value",
            "is_stackable",
            "max_stacks",
            "has_progression",
            "icon",
            "color_hex",
            "display_priority",
            "is_visible_to_others",
        ]
        read_only_fields = fields


class ConditionTemplateDetailSerializer(ConditionTemplateSerializer):
    """Detailed serializer including stages for progressive conditions."""

    stages = ConditionStageSerializer(many=True, read_only=True)

    class Meta(ConditionTemplateSerializer.Meta):
        fields = [*ConditionTemplateSerializer.Meta.fields, "stages"]


# =============================================================================
# Instance Serializers (Active Conditions)
# =============================================================================


class ConditionInstanceSerializer(serializers.ModelSerializer):
    """
    Serializer for active condition instances.

    Used for displaying conditions on a character's condition tab.
    """

    # Condition template info for display
    name = serializers.CharField(source="condition.name", read_only=True)
    description = serializers.CharField(source="condition.player_description", read_only=True)
    icon = serializers.CharField(source="condition.icon", read_only=True)
    color_hex = serializers.CharField(source="condition.color_hex", read_only=True)
    display_priority = serializers.IntegerField(source="condition.display_priority", read_only=True)
    is_visible_to_others = serializers.BooleanField(
        source="condition.is_visible_to_others", read_only=True
    )

    # Category info
    category_name = serializers.CharField(source="condition.category.name", read_only=True)
    is_negative = serializers.BooleanField(source="condition.category.is_negative", read_only=True)

    # Stage info for progressive conditions
    stage_name = serializers.CharField(source="current_stage.name", read_only=True, allow_null=True)
    stage_order = serializers.IntegerField(
        source="current_stage.stage_order", read_only=True, allow_null=True
    )
    total_stages = serializers.SerializerMethodField()

    # Stacking info
    max_stacks = serializers.IntegerField(source="condition.max_stacks", read_only=True)

    # Duration info
    duration_type = serializers.CharField(source="condition.default_duration_type", read_only=True)

    # Source info (who/what caused this)
    source_character_name = serializers.SerializerMethodField()
    source_power_name = serializers.SerializerMethodField()

    # Computed fields
    effective_severity = serializers.IntegerField(read_only=True)

    class Meta:
        model = ConditionInstance
        fields = [
            "id",
            # Template info
            "name",
            "description",
            "icon",
            "color_hex",
            "display_priority",
            "is_visible_to_others",
            # Category
            "category_name",
            "is_negative",
            # Current state
            "stacks",
            "max_stacks",
            "severity",
            "effective_severity",
            # Timing
            "duration_type",
            "rounds_remaining",
            "stage_rounds_remaining",
            "applied_at",
            "expires_at",
            # Stage info
            "stage_name",
            "stage_order",
            "total_stages",
            # Suppression
            "is_suppressed",
            "suppressed_until",
            # Source
            "source_character_name",
            "source_power_name",
            "source_description",
        ]
        read_only_fields = fields

    def get_total_stages(self, obj: ConditionInstance) -> int | None:
        """Get total number of stages for progressive conditions."""
        if obj.condition.has_progression:
            return obj.condition.stages.count()
        return None

    def get_source_character_name(self, obj: ConditionInstance) -> str | None:
        """Get the name of the source character."""
        if obj.source_character:
            return obj.source_character.key
        return None

    def get_source_power_name(self, obj: ConditionInstance) -> str | None:
        """Get the name of the source power."""
        if obj.source_power:
            return obj.source_power.name
        return None


class ConditionInstanceObserverSerializer(serializers.ModelSerializer):
    """
    Serializer for conditions as seen by other characters.

    Only shows visible conditions with observer-appropriate descriptions.
    """

    name = serializers.CharField(source="condition.name", read_only=True)
    description = serializers.CharField(source="condition.observer_description", read_only=True)
    icon = serializers.CharField(source="condition.icon", read_only=True)
    color_hex = serializers.CharField(source="condition.color_hex", read_only=True)
    category_name = serializers.CharField(source="condition.category.name", read_only=True)
    is_negative = serializers.BooleanField(source="condition.category.is_negative", read_only=True)

    # Stage info (visible to observers)
    stage_name = serializers.CharField(source="current_stage.name", read_only=True, allow_null=True)

    class Meta:
        model = ConditionInstance
        fields = [
            "id",
            "name",
            "description",
            "icon",
            "color_hex",
            "category_name",
            "is_negative",
            "stacks",
            "stage_name",
        ]
        read_only_fields = fields


# =============================================================================
# Summary Serializers (Aggregated Views)
# =============================================================================


class ConditionSummarySerializer(serializers.Serializer):
    """
    Summary of all conditions and their net effects on a character.

    Used for the character sheet conditions tab to show everything at once.
    """

    conditions = ConditionInstanceSerializer(many=True, read_only=True)
    total_conditions = serializers.IntegerField(read_only=True)
    negative_count = serializers.IntegerField(read_only=True)
    positive_count = serializers.IntegerField(read_only=True)

    # Net effects from all conditions
    blocked_capabilities = serializers.ListField(child=serializers.CharField(), read_only=True)
    capability_modifiers = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    check_modifiers = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    resistance_modifiers = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    turn_order_modifier = serializers.IntegerField(read_only=True)
    aggro_priority = serializers.IntegerField(read_only=True)

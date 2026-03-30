"""
Mechanics System Serializers

DRF serializers for game mechanics models.
"""

from rest_framework import serializers
from rest_framework_dataclasses.serializers import DataclassSerializer

from world.mechanics.models import (
    ChallengeApproach,
    ChallengeInstance,
    ChallengeTemplate,
    ChallengeTemplateConsequence,
    ChallengeTemplateProperty,
    CharacterModifier,
    ModifierCategory,
    ModifierSource,
    ModifierTarget,
    SituationChallengeLink,
    SituationInstance,
    SituationTemplate,
)
from world.mechanics.types import AvailableAction, CapabilitySource, ChallengeGroup


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


# ---------------------------------------------------------------------------
# Challenge Template serializers
# ---------------------------------------------------------------------------


class ChallengeTemplatePropertySerializer(serializers.ModelSerializer):
    """Nested serializer for challenge template properties."""

    property_name = serializers.CharField(source="property.name", read_only=True)

    class Meta:
        model = ChallengeTemplateProperty
        fields = ["property", "property_name", "value"]


class ChallengeApproachSerializer(serializers.ModelSerializer):
    """Nested serializer for challenge approaches."""

    application_name = serializers.CharField(source="application.name", read_only=True)
    check_type_name = serializers.CharField(source="check_type.name", read_only=True)

    class Meta:
        model = ChallengeApproach
        fields = [
            "id",
            "application",
            "application_name",
            "check_type",
            "check_type_name",
            "required_effect_property",
            "display_name",
            "custom_description",
            "action_template",
        ]


class ChallengeTemplateConsequenceSerializer(serializers.ModelSerializer):
    """Nested serializer for challenge template consequences."""

    consequence_name = serializers.CharField(source="consequence.name", read_only=True)

    class Meta:
        model = ChallengeTemplateConsequence
        fields = [
            "consequence",
            "consequence_name",
            "resolution_type",
            "resolution_duration_rounds",
        ]


class ChallengeTemplateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for challenge template list views."""

    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ChallengeTemplate
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "severity",
            "challenge_type",
            "discovery_type",
        ]


class ChallengeTemplateDetailSerializer(serializers.ModelSerializer):
    """Full serializer for challenge template detail views."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    template_properties = ChallengeTemplatePropertySerializer(
        source="cached_template_properties", many=True, read_only=True
    )
    approaches = ChallengeApproachSerializer(source="cached_approaches", many=True, read_only=True)
    template_consequences = ChallengeTemplateConsequenceSerializer(
        source="cached_consequences", many=True, read_only=True
    )

    class Meta:
        model = ChallengeTemplate
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "description_template",
            "goal",
            "severity",
            "challenge_type",
            "discovery_type",
            "template_properties",
            "approaches",
            "template_consequences",
        ]


# ---------------------------------------------------------------------------
# Challenge Instance serializer
# ---------------------------------------------------------------------------


class ChallengeInstanceSerializer(serializers.ModelSerializer):
    """Serializer for challenge instances."""

    template_name = serializers.CharField(source="template.name", read_only=True)
    location_name = serializers.CharField(source="location.db_key", read_only=True)
    target_object_name = serializers.CharField(source="target_object.db_key", read_only=True)

    class Meta:
        model = ChallengeInstance
        fields = [
            "id",
            "template",
            "template_name",
            "location",
            "location_name",
            "target_object",
            "target_object_name",
            "situation_instance",
            "is_active",
            "is_revealed",
            "created_at",
        ]


# ---------------------------------------------------------------------------
# Situation Template serializers
# ---------------------------------------------------------------------------


class SituationChallengeLinkSerializer(serializers.ModelSerializer):
    """Nested serializer for situation challenge links."""

    challenge_template_name = serializers.CharField(
        source="challenge_template.name", read_only=True
    )

    class Meta:
        model = SituationChallengeLink
        fields = [
            "challenge_template",
            "challenge_template_name",
            "display_order",
            "depends_on",
        ]


class SituationTemplateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for situation template list views."""

    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = SituationTemplate
        fields = ["id", "name", "category", "category_name"]


class SituationTemplateDetailSerializer(serializers.ModelSerializer):
    """Full serializer for situation template detail views."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    challenge_links = SituationChallengeLinkSerializer(
        source="cached_challenge_links", many=True, read_only=True
    )

    class Meta:
        model = SituationTemplate
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "description_template",
            "challenge_links",
        ]


# ---------------------------------------------------------------------------
# Situation Instance serializer
# ---------------------------------------------------------------------------


class SituationInstanceSerializer(serializers.ModelSerializer):
    """Serializer for situation instances."""

    template_name = serializers.CharField(source="template.name", read_only=True)
    location_name = serializers.CharField(source="location.db_key", read_only=True)

    class Meta:
        model = SituationInstance
        fields = [
            "id",
            "template",
            "template_name",
            "location",
            "location_name",
            "is_active",
            "created_by",
            "scene",
            "created_at",
        ]


# ---------------------------------------------------------------------------
# Dataclass serializers (available actions pipeline)
# ---------------------------------------------------------------------------


class CapabilitySourceSerializer(DataclassSerializer):
    """Serializer for CapabilitySource dataclass."""

    class Meta:
        dataclass = CapabilitySource
        exclude = ["prerequisite"]


class AvailableActionSerializer(DataclassSerializer):
    """Serializer for AvailableAction dataclass."""

    class Meta:
        dataclass = AvailableAction


class ChallengeGroupSerializer(DataclassSerializer):
    """Serializer for ChallengeGroup — actions grouped by challenge."""

    class Meta:
        dataclass = ChallengeGroup

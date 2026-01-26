"""
Skills API serializers.
"""

from rest_framework import serializers

from world.skills.models import (
    PathSkillSuggestion,
    Skill,
    SkillPointBudget,
    Specialization,
)
from world.traits.models import TraitCategory


class SpecializationSerializer(serializers.ModelSerializer):
    """Serializer for Specialization model."""

    parent_skill_id = serializers.IntegerField(source="parent_skill.id", read_only=True)
    parent_skill_name = serializers.CharField(source="parent_skill.name", read_only=True)

    class Meta:
        model = Specialization
        fields = [
            "id",
            "name",
            "description",
            "tooltip",
            "display_order",
            "is_active",
            "parent_skill_id",
            "parent_skill_name",
        ]


class SkillSerializer(serializers.ModelSerializer):
    """Serializer for Skill model with nested specializations."""

    name = serializers.CharField(source="trait.name", read_only=True)
    category = serializers.CharField(source="trait.category", read_only=True)
    category_display = serializers.SerializerMethodField()
    description = serializers.CharField(source="trait.description", read_only=True)
    specializations = SpecializationSerializer(many=True, read_only=True)

    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "category",
            "category_display",
            "description",
            "tooltip",
            "display_order",
            "is_active",
            "specializations",
        ]

    def get_category_display(self, obj: Skill) -> str:
        """Get the human-readable category label."""
        try:
            return TraitCategory(obj.trait.category).label
        except ValueError:
            return obj.trait.category


class SkillListSerializer(SkillSerializer):
    """Lighter serializer for skill lists without nested specializations.

    Inherits from SkillSerializer but excludes specializations field.
    """

    class Meta(SkillSerializer.Meta):
        fields = [
            "id",
            "name",
            "category",
            "category_display",
            "tooltip",
            "display_order",
            "is_active",
        ]


class PathSkillSuggestionSerializer(serializers.ModelSerializer):
    """Serializer for PathSkillSuggestion model."""

    path_id = serializers.IntegerField(source="character_path.id", read_only=True)
    path_name = serializers.CharField(source="character_path.name", read_only=True)
    skill_id = serializers.IntegerField(source="skill.id", read_only=True)
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_category = serializers.CharField(source="skill.category", read_only=True)

    class Meta:
        model = PathSkillSuggestion
        fields = [
            "id",
            "path_id",
            "path_name",
            "skill_id",
            "skill_name",
            "skill_category",
            "suggested_value",
            "display_order",
        ]


class SkillPointBudgetSerializer(serializers.ModelSerializer):
    """Serializer for SkillPointBudget configuration."""

    total_points = serializers.IntegerField(read_only=True)

    class Meta:
        model = SkillPointBudget
        fields = [
            "id",
            "path_points",
            "free_points",
            "total_points",
            "points_per_tier",
            "specialization_unlock_threshold",
            "max_skill_value",
            "max_specialization_value",
        ]

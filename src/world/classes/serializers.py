"""
Classes API serializers.
"""

from rest_framework import serializers

from world.classes.models import Aspect, CharacterClass, Path, PathAspect


class AspectSerializer(serializers.ModelSerializer):
    """Serializer for Aspect model."""

    class Meta:
        model = Aspect
        fields = [
            "id",
            "name",
            "description",
        ]


class PathAspectSerializer(serializers.ModelSerializer):
    """Serializer for PathAspect — aspect name only, weight is staff-only."""

    aspect_id = serializers.IntegerField(source="aspect.id", read_only=True)
    aspect_name = serializers.CharField(source="aspect.name", read_only=True)

    class Meta:
        model = PathAspect
        fields = [
            "id",
            "aspect_id",
            "aspect_name",
        ]


class PathListSerializer(serializers.ModelSerializer):
    """Lighter serializer for path lists without nested aspects."""

    stage_display = serializers.CharField(source="get_stage_display", read_only=True)

    class Meta:
        model = Path
        fields = [
            "id",
            "name",
            "description",
            "stage",
            "stage_display",
            "minimum_level",
            "is_active",
            "icon_url",
            "icon_name",
            "sort_order",
        ]


class PathSerializer(PathListSerializer):
    """Full serializer for path detail with aspects and parent paths."""

    aspects = PathAspectSerializer(source="cached_path_aspects", many=True, read_only=True)
    parent_path_ids = serializers.PrimaryKeyRelatedField(
        source="cached_parent_paths", many=True, read_only=True
    )

    class Meta(PathListSerializer.Meta):
        fields = [
            *PathListSerializer.Meta.fields,
            "aspects",
            "parent_path_ids",
        ]


class CharacterClassListSerializer(serializers.ModelSerializer):
    """Lighter serializer for character class lists."""

    class Meta:
        model = CharacterClass
        fields = [
            "id",
            "name",
            "description",
            "minimum_level",
        ]


class CharacterClassSerializer(CharacterClassListSerializer):
    """Full serializer for character class detail with core traits."""

    core_trait_ids = serializers.PrimaryKeyRelatedField(
        source="cached_core_traits", many=True, read_only=True
    )

    class Meta(CharacterClassListSerializer.Meta):
        fields = [
            *CharacterClassListSerializer.Meta.fields,
            "core_trait_ids",
        ]

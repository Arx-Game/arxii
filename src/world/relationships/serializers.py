"""DRF serializers for the relationships system."""

from rest_framework import serializers

from world.relationships.models import (
    CharacterRelationship,
    HybridRelationshipType,
    HybridRequirement,
    RelationshipCapstone,
    RelationshipChange,
    RelationshipCondition,
    RelationshipDevelopment,
    RelationshipTier,
    RelationshipTrack,
    RelationshipTrackProgress,
    RelationshipUpdate,
)


class RelationshipConditionSerializer(serializers.ModelSerializer):
    """Serializer for RelationshipCondition lookup table."""

    class Meta:
        model = RelationshipCondition
        fields = ["id", "name", "description", "display_order"]
        read_only_fields = fields


class RelationshipTierSerializer(serializers.ModelSerializer):
    """Serializer for RelationshipTier."""

    class Meta:
        model = RelationshipTier
        fields = ["id", "name", "tier_number", "point_threshold", "description"]
        read_only_fields = fields


class RelationshipTrackSerializer(serializers.ModelSerializer):
    """Serializer for RelationshipTrack with nested tiers."""

    cached_tiers = RelationshipTierSerializer(many=True, read_only=True)

    class Meta:
        model = RelationshipTrack
        fields = ["id", "name", "slug", "description", "sign", "cached_tiers"]
        read_only_fields = fields


class HybridRequirementSerializer(serializers.ModelSerializer):
    """Serializer for a single track/tier requirement on a hybrid type."""

    track_name = serializers.CharField(source="track.name", read_only=True)

    class Meta:
        model = HybridRequirement
        fields = ["track", "track_name", "minimum_tier"]
        read_only_fields = fields


class HybridRelationshipTypeSerializer(serializers.ModelSerializer):
    """Serializer for HybridRelationshipType with nested requirements."""

    cached_requirements = HybridRequirementSerializer(many=True, read_only=True)

    class Meta:
        model = HybridRelationshipType
        fields = ["id", "name", "slug", "description", "cached_requirements"]
        read_only_fields = fields


class RelationshipTrackProgressSerializer(serializers.ModelSerializer):
    """Serializer for track progress within a relationship."""

    track_name = serializers.CharField(source="track.name", read_only=True)
    track_sign = serializers.CharField(source="track.sign", read_only=True)
    current_tier_name = serializers.SerializerMethodField()
    temporary_points = serializers.IntegerField(read_only=True)
    total_points = serializers.IntegerField(read_only=True)

    class Meta:
        model = RelationshipTrackProgress
        fields = [
            "track",
            "track_name",
            "track_sign",
            "capacity",
            "developed_points",
            "temporary_points",
            "total_points",
            "current_tier_name",
        ]
        read_only_fields = fields

    def get_current_tier_name(self, obj: RelationshipTrackProgress) -> str | None:
        """Return the name of the current tier, or None if no tier reached."""
        tier = obj.current_tier
        return tier.name if tier else None


class RelationshipUpdateSerializer(serializers.ModelSerializer):
    """Serializer for relationship updates."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    track_name = serializers.CharField(source="track.name", read_only=True)

    class Meta:
        model = RelationshipUpdate
        fields = [
            "id",
            "author",
            "author_name",
            "title",
            "writeup",
            "track",
            "track_name",
            "points_earned",
            "coloring",
            "visibility",
            "is_first_impression",
            "linked_scene",
            "created_at",
        ]
        read_only_fields = fields


class RelationshipDevelopmentSerializer(serializers.ModelSerializer):
    """Serializer for relationship development updates."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    track_name = serializers.CharField(source="track.name", read_only=True)

    class Meta:
        model = RelationshipDevelopment
        fields = [
            "id",
            "author",
            "author_name",
            "title",
            "writeup",
            "track",
            "track_name",
            "points_earned",
            "xp_awarded",
            "visibility",
            "linked_scene",
            "created_at",
        ]
        read_only_fields = fields


class RelationshipCapstoneSerializer(serializers.ModelSerializer):
    """Serializer for relationship capstone events."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    track_name = serializers.CharField(source="track.name", read_only=True)

    class Meta:
        model = RelationshipCapstone
        fields = [
            "id",
            "author",
            "author_name",
            "title",
            "writeup",
            "track",
            "track_name",
            "points",
            "visibility",
            "linked_scene",
            "created_at",
        ]
        read_only_fields = fields


class RelationshipChangeSerializer(serializers.ModelSerializer):
    """Serializer for relationship changes (track-to-track point transfers)."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    source_track_name = serializers.CharField(source="source_track.name", read_only=True)
    target_track_name = serializers.CharField(source="target_track.name", read_only=True)

    class Meta:
        model = RelationshipChange
        fields = [
            "id",
            "author",
            "author_name",
            "title",
            "writeup",
            "source_track",
            "source_track_name",
            "target_track",
            "target_track_name",
            "points_moved",
            "visibility",
            "created_at",
        ]
        read_only_fields = fields


class CharacterRelationshipSerializer(serializers.ModelSerializer):
    """Full serializer for CharacterRelationship detail view."""

    source_name = serializers.CharField(source="source.character.db_key", read_only=True)
    target_name = serializers.CharField(source="target.character.db_key", read_only=True)
    cached_track_progress = RelationshipTrackProgressSerializer(many=True, read_only=True)
    absolute_value = serializers.IntegerField(read_only=True)
    developed_absolute_value = serializers.IntegerField(read_only=True)
    mechanical_bonus = serializers.FloatField(read_only=True)
    affection = serializers.IntegerField(read_only=True)

    class Meta:
        model = CharacterRelationship
        fields = [
            "id",
            "source",
            "source_name",
            "target",
            "target_name",
            "is_active",
            "is_pending",
            "is_deceitful",
            "cached_track_progress",
            "absolute_value",
            "developed_absolute_value",
            "mechanical_bonus",
            "affection",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CharacterRelationshipListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for CharacterRelationship list view."""

    source_name = serializers.CharField(source="source.character.db_key", read_only=True)
    target_name = serializers.CharField(source="target.character.db_key", read_only=True)
    absolute_value = serializers.IntegerField(read_only=True)
    developed_absolute_value = serializers.IntegerField(read_only=True)
    affection = serializers.IntegerField(read_only=True)

    class Meta:
        model = CharacterRelationship
        fields = [
            "id",
            "source",
            "source_name",
            "target",
            "target_name",
            "is_active",
            "is_pending",
            "absolute_value",
            "developed_absolute_value",
            "affection",
            "updated_at",
        ]
        read_only_fields = fields

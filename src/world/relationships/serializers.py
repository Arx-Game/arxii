"""DRF serializers for the relationships system."""

from rest_framework import serializers

from world.relationships.constants import FirstImpressionColoring, UpdateVisibility
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

# Choices accepted by the feedback write endpoints.
WRITEUP_TYPE_CHOICES = ["update", "development", "capstone"]


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

    tiers = RelationshipTierSerializer(source="cached_tiers", many=True, read_only=True)

    class Meta:
        model = RelationshipTrack
        fields = ["id", "name", "slug", "description", "sign", "tiers"]
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

    requirements = HybridRequirementSerializer(
        source="cached_requirements", many=True, read_only=True
    )

    class Meta:
        model = HybridRelationshipType
        fields = ["id", "name", "slug", "description", "requirements"]
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
    kudos_count = serializers.SerializerMethodField()
    viewer_has_kudosed = serializers.SerializerMethodField()

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
            "kudos_count",
            "viewer_has_kudosed",
        ]
        read_only_fields = fields

    def get_kudos_count(self, obj: RelationshipUpdate) -> int:
        """Return pre-annotated kudos count, or fall back to a query."""
        try:
            return obj.kudos_count  # set by viewset annotation
        except AttributeError:
            # Fallback for un-annotated single-object reads only. Any viewset
            # serving this serializer in a list/nested context must annotate
            # kudos_count via Count() to avoid per-row N+1 queries.
            return obj.writeupkudos_set.count()

    def get_viewer_has_kudosed(self, obj: RelationshipUpdate) -> bool:
        """Return True if the request user has kudosed this update."""
        try:
            return bool(obj.viewer_has_kudosed)  # set by viewset annotation
        except AttributeError:
            pass
        request = self.context.get("request")
        if request is None or not request.user.pk:
            return False
        # Fallback for un-annotated single-object reads only. Any viewset
        # serving this serializer in a list/nested context must annotate
        # viewer_has_kudosed via Exists() to avoid per-row N+1 queries.
        return obj.writeupkudos_set.filter(account_id=request.user.pk).exists()


class RelationshipDevelopmentSerializer(serializers.ModelSerializer):
    """Serializer for relationship development updates."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    track_name = serializers.CharField(source="track.name", read_only=True)
    kudos_count = serializers.SerializerMethodField()
    viewer_has_kudosed = serializers.SerializerMethodField()

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
            "kudos_count",
            "viewer_has_kudosed",
        ]
        read_only_fields = fields

    def get_kudos_count(self, obj: RelationshipDevelopment) -> int:
        """Return pre-annotated kudos count, or fall back to a query."""
        try:
            return obj.kudos_count  # set by viewset annotation
        except AttributeError:
            # Fallback for un-annotated single-object reads only. Any viewset
            # serving this serializer in a list/nested context must annotate
            # kudos_count via Count() to avoid per-row N+1 queries.
            return obj.writeupkudos_set.count()

    def get_viewer_has_kudosed(self, obj: RelationshipDevelopment) -> bool:
        """Return True if the request user has kudosed this development."""
        try:
            return bool(obj.viewer_has_kudosed)  # set by viewset annotation
        except AttributeError:
            pass
        request = self.context.get("request")
        if request is None or not request.user.pk:
            return False
        # Fallback for un-annotated single-object reads only. Any viewset
        # serving this serializer in a list/nested context must annotate
        # viewer_has_kudosed via Exists() to avoid per-row N+1 queries.
        return obj.writeupkudos_set.filter(account_id=request.user.pk).exists()


class RelationshipCapstoneSerializer(serializers.ModelSerializer):
    """Serializer for relationship capstone events."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    track_name = serializers.CharField(source="track.name", read_only=True)
    kudos_count = serializers.SerializerMethodField()
    viewer_has_kudosed = serializers.SerializerMethodField()

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
            "kudos_count",
            "viewer_has_kudosed",
        ]
        read_only_fields = fields

    def get_kudos_count(self, obj: RelationshipCapstone) -> int:
        """Return pre-annotated kudos count, or fall back to a query."""
        try:
            return obj.kudos_count  # set by viewset annotation
        except AttributeError:
            return obj.writeupkudos_set.count()

    def get_viewer_has_kudosed(self, obj: RelationshipCapstone) -> bool:
        """Return True if the request user has kudosed this capstone."""
        try:
            return bool(obj.viewer_has_kudosed)  # set by viewset annotation
        except AttributeError:
            pass
        request = self.context.get("request")
        if request is None or not request.user.pk:
            return False
        return obj.writeupkudos_set.filter(account_id=request.user.pk).exists()


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
    track_progress = RelationshipTrackProgressSerializer(
        source="cached_track_progress", many=True, read_only=True
    )
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
            "track_progress",
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
            "is_soul_tether",
            "soul_tether_role",
            "absolute_value",
            "developed_absolute_value",
            "affection",
            "updated_at",
        ]
        read_only_fields = fields


class FirstImpressionWriteSerializer(serializers.Serializer):
    """Serializer for creating a first impression."""

    target_persona_id = serializers.IntegerField()
    track_id = serializers.IntegerField()
    points = serializers.IntegerField(min_value=0)
    title = serializers.CharField()
    writeup = serializers.CharField()
    coloring = serializers.ChoiceField(
        choices=FirstImpressionColoring.choices,
        required=False,
        default=FirstImpressionColoring.NEUTRAL,
    )
    visibility = serializers.ChoiceField(
        choices=UpdateVisibility.choices,
        required=False,
        default=UpdateVisibility.PRIVATE,
    )


class DevelopmentWriteSerializer(serializers.Serializer):
    """Serializer for creating a relationship development update."""

    target_persona_id = serializers.IntegerField()
    track_id = serializers.IntegerField()
    points = serializers.IntegerField(min_value=0)
    title = serializers.CharField()
    writeup = serializers.CharField()
    xp_awarded = serializers.IntegerField(required=False, default=0)
    visibility = serializers.ChoiceField(
        choices=UpdateVisibility.choices,
        required=False,
        default=UpdateVisibility.PRIVATE,
    )


class CapstoneWriteSerializer(serializers.Serializer):
    """Serializer for creating a relationship capstone event."""

    target_persona_id = serializers.IntegerField()
    track_id = serializers.IntegerField()
    points = serializers.IntegerField(min_value=0)
    title = serializers.CharField()
    writeup = serializers.CharField()
    visibility = serializers.ChoiceField(
        choices=UpdateVisibility.choices,
        required=False,
        default=UpdateVisibility.SHARED,
    )


class RedistributeWriteSerializer(serializers.Serializer):
    """Serializer for redistributing relationship points between tracks."""

    target_persona_id = serializers.IntegerField()
    source_track_id = serializers.IntegerField()
    target_track_id = serializers.IntegerField()
    points = serializers.IntegerField(min_value=0)
    title = serializers.CharField()
    writeup = serializers.CharField()
    visibility = serializers.ChoiceField(
        choices=UpdateVisibility.choices,
        required=False,
        default=UpdateVisibility.PRIVATE,
    )


class WriteupKudosWriteSerializer(serializers.Serializer):
    """Validate input for the kudos endpoint.

    ``writeup_type`` selects which of the three writeup models the ID refers to.
    ``writeup_id`` is the pk of that writeup. Existence is validated inside the
    action (raises WriteupFeedbackError → mapped to a 400 response body).
    """

    writeup_type = serializers.ChoiceField(choices=WRITEUP_TYPE_CHOICES)
    writeup_id = serializers.IntegerField()


class WriteupComplaintWriteSerializer(serializers.Serializer):
    """Validate input for the complaint endpoint.

    Same shape as WriteupKudosWriteSerializer plus a mandatory ``reason`` field.
    Permissions (visibility check) are enforced inside the action / service.
    """

    writeup_type = serializers.ChoiceField(choices=WRITEUP_TYPE_CHOICES)
    writeup_id = serializers.IntegerField()
    reason = serializers.CharField(allow_blank=False)

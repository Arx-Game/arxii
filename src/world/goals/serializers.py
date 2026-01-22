"""Serializers for the goals system API."""

from rest_framework import serializers

from world.goals.models import CharacterGoal, GoalDomain, GoalJournal, GoalRevision

# Maximum total points a character can allocate across all goals
MAX_GOAL_POINTS = 30


class GoalDomainSerializer(serializers.ModelSerializer):
    """Serializer for GoalDomain lookup records."""

    class Meta:
        model = GoalDomain
        fields = ["id", "name", "slug", "description", "display_order", "is_optional"]
        read_only_fields = fields


class CharacterGoalSerializer(serializers.ModelSerializer):
    """Serializer for CharacterGoal records."""

    domain_name = serializers.CharField(source="domain.name", read_only=True)
    domain_slug = serializers.CharField(source="domain.slug", read_only=True)

    class Meta:
        model = CharacterGoal
        fields = [
            "id",
            "domain",
            "domain_name",
            "domain_slug",
            "points",
            "notes",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class GoalInputSerializer(serializers.Serializer):
    """
    Serializer for a single goal input in the update request.

    Uses PrimaryKeyRelatedField for domain lookup with built-in validation.
    """

    domain = serializers.PrimaryKeyRelatedField(queryset=GoalDomain.objects.all())
    points = serializers.IntegerField(min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_points(self, value: int) -> int:
        """Validate points is non-negative."""
        if value < 0:
            msg = "Points cannot be negative."
            raise serializers.ValidationError(msg)
        return value


class CharacterGoalUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating all character goals at once.

    Uses nested GoalInputSerializer for proper validation with PrimaryKeyRelatedField.
    Frontend sends domain IDs (not slugs) for standard DRF related field handling.
    """

    goals = GoalInputSerializer(many=True)

    def validate_goals(self, value: list[dict]) -> list[dict]:
        """Validate goal allocations."""
        total_points = sum(g.get("points", 0) for g in value)
        if total_points > MAX_GOAL_POINTS:
            msg = f"Total points ({total_points}) exceeds maximum of {MAX_GOAL_POINTS}."
            raise serializers.ValidationError(msg)

        # Check for duplicate domains
        domain_ids = [g["domain"].id for g in value]
        if len(domain_ids) != len(set(domain_ids)):
            duplicates = [d for d in domain_ids if domain_ids.count(d) > 1]
            dup_names = [GoalDomain.objects.get(id=d).name for d in set(duplicates)]
            msg = f"Duplicate domains in request: {', '.join(dup_names)}"
            raise serializers.ValidationError(msg)

        return value


class GoalJournalSerializer(serializers.ModelSerializer):
    """Serializer for GoalJournal records."""

    domain_name = serializers.CharField(
        source="domain.name", read_only=True, allow_null=True, default=None
    )
    domain_slug = serializers.CharField(
        source="domain.slug", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = GoalJournal
        fields = [
            "id",
            "domain",
            "domain_name",
            "domain_slug",
            "title",
            "content",
            "is_public",
            "xp_awarded",
            "created_at",
        ]
        read_only_fields = ["id", "xp_awarded", "created_at"]


class GoalJournalCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new journal entry.

    Uses PrimaryKeyRelatedField for domain lookup with built-in validation.
    """

    domain = serializers.PrimaryKeyRelatedField(
        queryset=GoalDomain.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = GoalJournal
        fields = ["domain", "title", "content", "is_public"]

    def create(self, validated_data: dict) -> GoalJournal:
        """Create journal entry with XP award."""
        # XP awarded could be calculated based on content length, etc.
        # For now, a flat 1 XP per journal entry
        xp_awarded = 1

        return GoalJournal.objects.create(
            xp_awarded=xp_awarded,
            **validated_data,
        )


class GoalRevisionSerializer(serializers.ModelSerializer):
    """Serializer for GoalRevision records."""

    can_revise = serializers.SerializerMethodField()

    class Meta:
        model = GoalRevision
        fields = ["last_revised_at", "can_revise"]
        read_only_fields = fields

    def get_can_revise(self, obj: GoalRevision) -> bool:
        """Check if character can revise goals."""
        return obj.can_revise()

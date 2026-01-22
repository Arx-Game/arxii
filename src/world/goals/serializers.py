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
        fields = ["id", "domain", "domain_name", "domain_slug", "points", "notes", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class CharacterGoalUpdateSerializer(serializers.Serializer):
    """Serializer for updating all character goals at once."""

    goals = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of {domain_slug, points, notes} objects.",
    )

    def validate_goals(self, value: list[dict]) -> list[dict]:
        """Validate goal allocations."""
        total_points = sum(g.get("points", 0) for g in value)
        if total_points > MAX_GOAL_POINTS:
            msg = f"Total points ({total_points}) exceeds maximum of {MAX_GOAL_POINTS}."
            raise serializers.ValidationError(msg)

        # Validate each goal entry
        valid_slugs = set(GoalDomain.objects.values_list("slug", flat=True))
        for goal in value:
            if "domain_slug" not in goal:
                msg = "Each goal must have a domain_slug."
                raise serializers.ValidationError(msg)
            if goal["domain_slug"] not in valid_slugs:
                msg = f"Invalid domain slug: {goal['domain_slug']}"
                raise serializers.ValidationError(msg)
            if goal.get("points", 0) < 0:
                msg = "Points cannot be negative."
                raise serializers.ValidationError(msg)

        return value


class GoalJournalSerializer(serializers.ModelSerializer):
    """Serializer for GoalJournal records."""

    domain_name = serializers.CharField(source="domain.name", read_only=True)
    domain_slug = serializers.CharField(source="domain.slug", read_only=True)

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
    """Serializer for creating a new journal entry."""

    domain_slug = serializers.SlugField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = GoalJournal
        fields = ["domain_slug", "title", "content", "is_public"]

    def validate_domain_slug(self, value: str | None) -> str | None:
        """Validate domain slug if provided."""
        if value:
            if not GoalDomain.objects.filter(slug=value).exists():
                msg = f"Invalid domain slug: {value}"
                raise serializers.ValidationError(msg)
        return value

    def create(self, validated_data: dict) -> GoalJournal:
        """Create journal entry, looking up domain by slug."""
        domain_slug = validated_data.pop("domain_slug", None)
        domain = None
        if domain_slug:
            domain = GoalDomain.objects.get(slug=domain_slug)

        # XP awarded could be calculated based on content length, etc.
        # For now, a flat 1 XP per journal entry
        xp_awarded = 1

        return GoalJournal.objects.create(
            domain=domain,
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


class CharacterGoalSummarySerializer(serializers.Serializer):
    """Serializer for a character's complete goal summary."""

    goals = CharacterGoalSerializer(many=True)
    total_points = serializers.IntegerField()
    points_remaining = serializers.IntegerField()
    revision = GoalRevisionSerializer(allow_null=True)

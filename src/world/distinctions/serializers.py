"""
Serializers for the distinctions system API.

This module provides serializers for both lookup tables (read-only)
and character-specific distinction data.
"""

from rest_framework import serializers

from world.distinctions.models import (
    CharacterDistinction,
    CharacterDistinctionOther,
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
    DistinctionMutualExclusion,
    DistinctionTag,
)

# =============================================================================
# Lookup Table Serializers (Read-Only)
# =============================================================================


class DistinctionCategorySerializer(serializers.ModelSerializer):
    """Serializer for DistinctionCategory lookup records."""

    class Meta:
        model = DistinctionCategory
        fields = ["id", "name", "slug", "description", "display_order"]
        read_only_fields = fields


class DistinctionTagSerializer(serializers.ModelSerializer):
    """Serializer for DistinctionTag lookup records."""

    class Meta:
        model = DistinctionTag
        fields = ["id", "name", "slug"]
        read_only_fields = fields


class DistinctionEffectSerializer(serializers.ModelSerializer):
    """Serializer for DistinctionEffect records."""

    effect_type_display = serializers.CharField(
        source="get_effect_type_display",
        read_only=True,
    )

    class Meta:
        model = DistinctionEffect
        fields = [
            "id",
            "effect_type",
            "effect_type_display",
            "target",
            "value_per_rank",
            "scaling_values",
            "description",
        ]
        read_only_fields = fields


# =============================================================================
# Distinction Serializers
# =============================================================================


class DistinctionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Distinction list views."""

    category_slug = serializers.CharField(
        source="category.slug",
        read_only=True,
    )
    tags = DistinctionTagSerializer(many=True, read_only=True)
    effects_summary = serializers.SerializerMethodField()
    is_locked = serializers.SerializerMethodField()
    lock_reason = serializers.SerializerMethodField()

    class Meta:
        model = Distinction
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category_slug",
            "cost_per_rank",
            "max_rank",
            "is_variant_parent",
            "allow_other",
            "tags",
            "effects_summary",
            "is_locked",
            "lock_reason",
        ]
        read_only_fields = fields

    def get_effects_summary(self, obj: Distinction) -> list[str]:
        """Return a list of effect descriptions for this distinction."""
        return [effect.description for effect in obj.effects.all() if effect.description]

    def get_is_locked(self, obj: Distinction) -> bool:
        """Check if this distinction is locked due to mutual exclusion with draft."""
        draft = self.context.get("draft")
        if not draft:
            return False

        # Read from JSON data, not a related manager
        draft_distinctions = draft.draft_data.get("distinctions", [])
        draft_distinction_ids = {d.get("distinction_id") for d in draft_distinctions}

        # Get excluded distinctions for this one
        excluded = DistinctionMutualExclusion.get_excluded_for(obj)
        excluded_ids = {d.id for d in excluded}

        # Check if any of the character's distinctions are in the excluded set
        return bool(draft_distinction_ids & excluded_ids)

    def get_lock_reason(self, obj: Distinction) -> str | None:
        """Return the reason this distinction is locked, if any."""
        draft = self.context.get("draft")
        if not draft:
            return None

        # Read from JSON data, not a related manager
        draft_distinctions = draft.draft_data.get("distinctions", [])
        draft_distinction_ids = {d.get("distinction_id") for d in draft_distinctions}

        # Get excluded distinctions for this one
        excluded = DistinctionMutualExclusion.get_excluded_for(obj)

        # Find which of the character's distinctions caused the exclusion
        for exc in excluded:
            if exc.id in draft_distinction_ids:
                return f"Mutually exclusive with {exc.name}"

        return None


class DistinctionDetailSerializer(serializers.ModelSerializer):
    """Full serializer for Distinction detail views."""

    category = DistinctionCategorySerializer(read_only=True)
    tags = DistinctionTagSerializer(many=True, read_only=True)
    effects = DistinctionEffectSerializer(many=True, read_only=True)
    variants = serializers.SerializerMethodField()
    prerequisite_description = serializers.SerializerMethodField()

    class Meta:
        model = Distinction
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category",
            "cost_per_rank",
            "max_rank",
            "is_variant_parent",
            "allow_other",
            "tags",
            "effects",
            "variants",
            "prerequisite_description",
        ]
        read_only_fields = fields

    def get_variants(self, obj: Distinction) -> list[dict] | None:
        """Return child variants if this is a variant parent."""
        if not obj.is_variant_parent:
            return None

        variants = obj.variants.filter(is_active=True)
        return DistinctionListSerializer(
            variants,
            many=True,
            context=self.context,
        ).data

    def get_prerequisite_description(self, obj: Distinction) -> str | None:
        """Return a human-readable description of prerequisites."""
        prerequisites = obj.prerequisites.all()
        if not prerequisites:
            return None

        # Combine all prerequisite descriptions
        descriptions = [p.description for p in prerequisites if p.description]
        if not descriptions:
            return None

        return "; ".join(descriptions)


# =============================================================================
# Character Distinction Serializers
# =============================================================================


class CharacterDistinctionSerializer(serializers.ModelSerializer):
    """Serializer for CharacterDistinction records."""

    distinction = DistinctionListSerializer(read_only=True)
    distinction_id = serializers.PrimaryKeyRelatedField(
        queryset=Distinction.objects.filter(is_active=True),
        source="distinction",
        write_only=True,
    )
    total_cost = serializers.SerializerMethodField()
    is_automatic = serializers.SerializerMethodField()

    class Meta:
        model = CharacterDistinction
        fields = [
            "id",
            "distinction",
            "distinction_id",
            "rank",
            "notes",
            "origin",
            "is_temporary",
            "total_cost",
            "is_automatic",
        ]
        read_only_fields = ["id", "origin", "is_temporary"]

    def get_total_cost(self, obj: CharacterDistinction) -> int:
        """Calculate total cost for this character's distinction at their rank."""
        return obj.calculate_total_cost()

    def get_is_automatic(self, obj: CharacterDistinction) -> bool:
        """Check if this distinction was automatically granted."""
        return obj.distinction.is_automatic


class CharacterDistinctionOtherSerializer(serializers.ModelSerializer):
    """Serializer for CharacterDistinctionOther (freeform 'Other') records."""

    parent_distinction_name = serializers.CharField(
        source="parent_distinction.name",
        read_only=True,
    )

    class Meta:
        model = CharacterDistinctionOther
        fields = [
            "id",
            "parent_distinction",
            "parent_distinction_name",
            "freeform_text",
            "status",
            "staff_mapped_distinction",
        ]
        read_only_fields = ["id", "status", "staff_mapped_distinction"]

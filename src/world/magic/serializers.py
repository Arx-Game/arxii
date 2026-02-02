"""
Serializers for the magic system API.

This module provides serializers for both lookup tables (read-only)
and character-specific magic data.

Affinities and Resonances are now ModifierType entries in the mechanics app.
"""

from rest_framework import serializers

from world.magic.models import (
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterGift,
    CharacterResonance,
    EffectType,
    Gift,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
    ResonanceAssociation,
    Restriction,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadJournal,
    ThreadResonance,
    ThreadType,
)
from world.mechanics.models import ModifierType

# =============================================================================
# Lookup Table Serializers (Read-Only)
# =============================================================================


class ModifierTypeSerializer(serializers.ModelSerializer):
    """Serializer for ModifierType records (affinities and resonances)."""

    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ModifierType
        fields = ["id", "name", "category", "category_name", "description"]
        read_only_fields = fields


class ThreadTypeSerializer(serializers.ModelSerializer):
    """Serializer for ThreadType lookup records."""

    grants_resonance_name = serializers.CharField(
        source="grants_resonance.name",
        read_only=True,
        allow_null=True,
    )
    grants_resonance_detail = ModifierTypeSerializer(
        source="grants_resonance",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = ThreadType
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "romantic_threshold",
            "trust_threshold",
            "rivalry_threshold",
            "protective_threshold",
            "enmity_threshold",
            "grants_resonance",
            "grants_resonance_name",
            "grants_resonance_detail",
        ]
        read_only_fields = fields


class TechniqueStyleSerializer(serializers.ModelSerializer):
    """Serializer for TechniqueStyle lookup records."""

    class Meta:
        model = TechniqueStyle
        fields = ["id", "name", "description"]
        read_only_fields = fields


class EffectTypeSerializer(serializers.ModelSerializer):
    """Serializer for EffectType lookup records."""

    class Meta:
        model = EffectType
        fields = [
            "id",
            "name",
            "description",
            "base_power",
            "base_anima_cost",
            "has_power_scaling",
        ]
        read_only_fields = fields


class RestrictionSerializer(serializers.ModelSerializer):
    """Serializer for Restriction lookup records."""

    # Use cached property to work with Prefetch(to_attr=) for SharedMemoryModel
    allowed_effect_type_ids = serializers.SerializerMethodField()

    class Meta:
        model = Restriction
        fields = ["id", "name", "description", "power_bonus", "allowed_effect_type_ids"]
        read_only_fields = fields

    def get_allowed_effect_type_ids(self, obj) -> list[int]:
        """Get effect type IDs, using cached property if available."""
        return [et.id for et in obj.cached_allowed_effect_types]


class ResonanceAssociationSerializer(serializers.ModelSerializer):
    """Serializer for ResonanceAssociation lookup records."""

    class Meta:
        model = ResonanceAssociation
        fields = ["id", "name", "description", "category"]
        read_only_fields = fields


# =============================================================================
# Technique Serializers
# =============================================================================


class TechniqueSerializer(serializers.ModelSerializer):
    """Serializer for Technique records with calculated fields."""

    calculated_power = serializers.IntegerField(read_only=True)
    tier = serializers.IntegerField(read_only=True)
    restriction_ids = serializers.PrimaryKeyRelatedField(
        source="restrictions",
        many=True,
        queryset=Restriction.objects.all(),
    )

    class Meta:
        model = Technique
        fields = [
            "id",
            "name",
            "gift",
            "style",
            "effect_type",
            "restriction_ids",
            "level",
            "anima_cost",
            "description",
            "calculated_power",
            "tier",
        ]


# =============================================================================
# Gift Serializers
# =============================================================================


class GiftSerializer(serializers.ModelSerializer):
    """Serializer for Gift records with nested techniques."""

    affinity_name = serializers.CharField(
        source="affinity.name",
        read_only=True,
    )
    # Use cached properties to work with Prefetch(to_attr=) for SharedMemoryModel
    resonances = serializers.SerializerMethodField()
    techniques = serializers.SerializerMethodField()
    # Use annotated field from queryset (avoids N+1)
    technique_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Gift
        fields = [
            "id",
            "name",
            "affinity",
            "affinity_name",
            "description",
            "resonances",
            "techniques",
            "technique_count",
        ]
        read_only_fields = fields

    def get_resonances(self, obj) -> list[dict]:
        """Get resonances using cached property."""
        return ModifierTypeSerializer(obj.cached_resonances, many=True).data

    def get_techniques(self, obj) -> list[dict]:
        """Get techniques using cached property."""
        return TechniqueSerializer(obj.cached_techniques, many=True).data


class GiftCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Gift records."""

    MIN_RESONANCES = 1
    MAX_RESONANCES = 2

    resonance_ids = serializers.PrimaryKeyRelatedField(
        source="resonances",
        many=True,
        queryset=ModifierType.objects.filter(category__name="resonance"),
    )

    class Meta:
        model = Gift
        fields = ["id", "name", "affinity", "resonance_ids", "description"]

    def validate_resonance_ids(self, value):
        """Validate that gift has 1-2 resonances."""
        if len(value) < self.MIN_RESONANCES:
            msg = "Gift must have at least 1 resonance."
            raise serializers.ValidationError(msg)
        if len(value) > self.MAX_RESONANCES:
            msg = "Gift can have at most 2 resonances."
            raise serializers.ValidationError(msg)
        return value


class GiftListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Gift list views."""

    affinity_name = serializers.CharField(
        source="affinity.name",
        read_only=True,
    )
    # Use annotated field from queryset (avoids N+1)
    technique_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Gift
        fields = [
            "id",
            "name",
            "affinity",
            "affinity_name",
            "description",
            "technique_count",
        ]
        read_only_fields = fields


# =============================================================================
# Character Magic State Serializers
# =============================================================================


class CharacterAuraSerializer(serializers.ModelSerializer):
    """Serializer for CharacterAura records."""

    dominant_affinity = serializers.CharField(read_only=True)
    dominant_affinity_display = serializers.SerializerMethodField()

    class Meta:
        model = CharacterAura
        fields = [
            "id",
            "character",
            "celestial",
            "primal",
            "abyssal",
            "dominant_affinity",
            "dominant_affinity_display",
            "updated_at",
        ]
        read_only_fields = ["id", "dominant_affinity", "dominant_affinity_display", "updated_at"]

    def get_dominant_affinity_display(self, obj: CharacterAura) -> str:
        """Return the display label for the dominant affinity."""
        return obj.dominant_affinity.label


class CharacterAuraCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating CharacterAura."""

    class Meta:
        model = CharacterAura
        fields = ["character", "celestial", "primal", "abyssal"]

    def validate(self, attrs):
        """Ensure percentages sum to 100."""
        required_total = 100
        celestial = attrs.get("celestial", 0)
        primal = attrs.get("primal", 0)
        abyssal = attrs.get("abyssal", 0)
        total = celestial + primal + abyssal
        if total != required_total:
            msg = f"Aura percentages must sum to {required_total}, got {total}."
            raise serializers.ValidationError(msg)
        return attrs


class CharacterResonanceSerializer(serializers.ModelSerializer):
    """Serializer for CharacterResonance records."""

    resonance_name = serializers.CharField(
        source="resonance.name",
        read_only=True,
    )
    resonance_detail = ModifierTypeSerializer(source="resonance", read_only=True)
    scope_display = serializers.CharField(
        source="get_scope_display",
        read_only=True,
    )
    strength_display = serializers.CharField(
        source="get_strength_display",
        read_only=True,
    )

    class Meta:
        model = CharacterResonance
        fields = [
            "id",
            "character",
            "resonance",
            "resonance_name",
            "resonance_detail",
            "scope",
            "scope_display",
            "strength",
            "strength_display",
            "flavor_text",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class CharacterGiftSerializer(serializers.ModelSerializer):
    """Serializer for CharacterGift records."""

    gift_name = serializers.CharField(
        source="gift.name",
        read_only=True,
    )
    gift_detail = GiftSerializer(source="gift", read_only=True)

    class Meta:
        model = CharacterGift
        fields = [
            "id",
            "character",
            "gift",
            "gift_name",
            "gift_detail",
            "acquired_at",
        ]
        read_only_fields = ["id", "acquired_at"]


class CharacterAnimaSerializer(serializers.ModelSerializer):
    """Serializer for CharacterAnima records."""

    class Meta:
        model = CharacterAnima
        fields = [
            "id",
            "character",
            "current",
            "maximum",
            "last_recovery",
        ]
        read_only_fields = ["id", "last_recovery"]


class CharacterAnimaRitualSerializer(serializers.ModelSerializer):
    """Serializer for CharacterAnimaRitual records."""

    stat_name = serializers.CharField(source="stat.name", read_only=True)
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    specialization_name = serializers.SerializerMethodField()
    resonance_name = serializers.CharField(source="resonance.name", read_only=True)
    resonance_detail = ModifierTypeSerializer(source="resonance", read_only=True)

    class Meta:
        model = CharacterAnimaRitual
        fields = [
            "id",
            "character",
            "stat",
            "stat_name",
            "skill",
            "skill_name",
            "specialization",
            "specialization_name",
            "resonance",
            "resonance_name",
            "resonance_detail",
            "description",
        ]
        read_only_fields = ["id"]

    def get_specialization_name(self, obj: CharacterAnimaRitual) -> str | None:
        """Get the specialization name if present."""
        if obj.specialization:
            return obj.specialization.name
        return None


# =============================================================================
# Thread (Relationship) Serializers
# =============================================================================


class ThreadResonanceSerializer(serializers.ModelSerializer):
    """Serializer for ThreadResonance records."""

    resonance_name = serializers.CharField(
        source="resonance.name",
        read_only=True,
    )
    resonance_detail = ModifierTypeSerializer(source="resonance", read_only=True)

    class Meta:
        model = ThreadResonance
        fields = [
            "id",
            "thread",
            "resonance",
            "resonance_name",
            "resonance_detail",
            "strength",
            "flavor_text",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ThreadJournalSerializer(serializers.ModelSerializer):
    """Serializer for ThreadJournal records."""

    author_name = serializers.CharField(
        source="author.db_key",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = ThreadJournal
        fields = [
            "id",
            "thread",
            "author",
            "author_name",
            "content",
            "romantic_change",
            "trust_change",
            "rivalry_change",
            "protective_change",
            "enmity_change",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ThreadSerializer(serializers.ModelSerializer):
    """Serializer for Thread records."""

    initiator_name = serializers.CharField(
        source="initiator.db_key",
        read_only=True,
    )
    receiver_name = serializers.CharField(
        source="receiver.db_key",
        read_only=True,
    )
    matching_types = serializers.SerializerMethodField()
    resonances = ThreadResonanceSerializer(many=True, read_only=True)

    class Meta:
        model = Thread
        fields = [
            "id",
            "initiator",
            "initiator_name",
            "receiver",
            "receiver_name",
            "romantic",
            "trust",
            "rivalry",
            "protective",
            "enmity",
            "is_soul_tether",
            "matching_types",
            "resonances",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "matching_types", "created_at", "updated_at"]

    def get_matching_types(self, obj: Thread) -> list[dict]:
        """Return the thread types this thread qualifies for."""
        return ThreadTypeSerializer(obj.get_matching_types(), many=True).data


class ThreadListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Thread list views."""

    initiator_name = serializers.CharField(
        source="initiator.db_key",
        read_only=True,
    )
    receiver_name = serializers.CharField(
        source="receiver.db_key",
        read_only=True,
    )

    class Meta:
        model = Thread
        fields = [
            "id",
            "initiator",
            "initiator_name",
            "receiver",
            "receiver_name",
            "romantic",
            "trust",
            "rivalry",
            "protective",
            "enmity",
            "is_soul_tether",
            "updated_at",
        ]
        read_only_fields = fields


# =============================================================================
# Motif Serializers
# =============================================================================


class MotifResonanceAssociationSerializer(serializers.ModelSerializer):
    """Serializer for MotifResonanceAssociation records."""

    association_name = serializers.CharField(source="association.name", read_only=True)

    class Meta:
        model = MotifResonanceAssociation
        fields = ["id", "association", "association_name"]
        read_only_fields = ["id", "association_name"]


class MotifResonanceSerializer(serializers.ModelSerializer):
    """Serializer for MotifResonance records with nested associations."""

    resonance_name = serializers.CharField(source="resonance.name", read_only=True)
    associations = MotifResonanceAssociationSerializer(many=True, read_only=True)

    class Meta:
        model = MotifResonance
        fields = ["id", "resonance", "resonance_name", "is_from_gift", "associations"]
        read_only_fields = ["id", "resonance_name"]


class MotifSerializer(serializers.ModelSerializer):
    """Serializer for Motif records with nested resonances."""

    resonances = MotifResonanceSerializer(many=True, read_only=True)

    class Meta:
        model = Motif
        fields = ["id", "description", "resonances"]
        read_only_fields = ["id"]

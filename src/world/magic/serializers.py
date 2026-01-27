"""
Serializers for the magic system API.

This module provides serializers for both lookup tables (read-only)
and character-specific magic data.

Affinities and Resonances are now ModifierType entries in the mechanics app.
"""

from rest_framework import serializers

from world.magic.models import (
    AnimaRitualType,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterGift,
    CharacterPower,
    CharacterResonance,
    Gift,
    IntensityTier,
    Power,
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


class IntensityTierSerializer(serializers.ModelSerializer):
    """Serializer for IntensityTier lookup records."""

    class Meta:
        model = IntensityTier
        fields = ["id", "name", "threshold", "control_modifier", "description"]
        read_only_fields = fields


class AnimaRitualTypeSerializer(serializers.ModelSerializer):
    """Serializer for AnimaRitualType lookup records."""

    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )

    class Meta:
        model = AnimaRitualType
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "category_display",
            "description",
            "base_recovery",
        ]
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


# =============================================================================
# Gift & Power Serializers
# =============================================================================


class PowerSerializer(serializers.ModelSerializer):
    """Serializer for Power records."""

    affinity_name = serializers.CharField(
        source="affinity.name",
        read_only=True,
    )
    resonances = ModifierTypeSerializer(many=True, read_only=True)

    class Meta:
        model = Power
        fields = [
            "id",
            "name",
            "slug",
            "gift",
            "affinity",
            "affinity_name",
            "base_intensity",
            "base_control",
            "anima_cost",
            "level_requirement",
            "description",
            "resonances",
        ]
        read_only_fields = fields


class GiftSerializer(serializers.ModelSerializer):
    """Serializer for Gift records."""

    affinity_name = serializers.CharField(
        source="affinity.name",
        read_only=True,
    )
    resonances = ModifierTypeSerializer(many=True, read_only=True)
    powers = PowerSerializer(many=True, read_only=True)

    class Meta:
        model = Gift
        fields = [
            "id",
            "name",
            "slug",
            "affinity",
            "affinity_name",
            "description",
            "level_requirement",
            "resonances",
            "powers",
        ]
        read_only_fields = fields


class GiftListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Gift list views (without nested powers)."""

    affinity_name = serializers.CharField(
        source="affinity.name",
        read_only=True,
    )
    power_count = serializers.IntegerField(
        source="powers.count",
        read_only=True,
    )

    class Meta:
        model = Gift
        fields = [
            "id",
            "name",
            "slug",
            "affinity",
            "affinity_name",
            "description",
            "level_requirement",
            "power_count",
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
            "notes",
        ]
        read_only_fields = ["id", "acquired_at"]


class CharacterPowerSerializer(serializers.ModelSerializer):
    """Serializer for CharacterPower records."""

    power_name = serializers.CharField(
        source="power.name",
        read_only=True,
    )
    power_detail = PowerSerializer(source="power", read_only=True)

    class Meta:
        model = CharacterPower
        fields = [
            "id",
            "character",
            "power",
            "power_name",
            "power_detail",
            "unlocked_at",
            "times_used",
            "notes",
        ]
        read_only_fields = ["id", "unlocked_at"]


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

    ritual_type_name = serializers.CharField(
        source="ritual_type.name",
        read_only=True,
    )
    ritual_type_detail = AnimaRitualTypeSerializer(source="ritual_type", read_only=True)

    class Meta:
        model = CharacterAnimaRitual
        fields = [
            "id",
            "character",
            "ritual_type",
            "ritual_type_name",
            "ritual_type_detail",
            "personal_description",
            "is_primary",
            "times_performed",
            "created_at",
        ]
        read_only_fields = ["id", "times_performed", "created_at"]


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

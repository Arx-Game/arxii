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
    Gift,
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


# =============================================================================
# Gift Serializers
# =============================================================================


class GiftSerializer(serializers.ModelSerializer):
    """Serializer for Gift records."""

    affinity_name = serializers.CharField(
        source="affinity.name",
        read_only=True,
    )
    resonances = ModifierTypeSerializer(many=True, read_only=True)
    technique_count = serializers.IntegerField(
        source="techniques.count",
        read_only=True,
    )

    class Meta:
        model = Gift
        fields = [
            "id",
            "name",
            "affinity",
            "affinity_name",
            "description",
            "resonances",
            "technique_count",
        ]
        read_only_fields = fields


class GiftListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Gift list views."""

    affinity_name = serializers.CharField(
        source="affinity.name",
        read_only=True,
    )
    technique_count = serializers.IntegerField(
        source="techniques.count",
        read_only=True,
    )

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

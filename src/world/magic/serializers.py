"""
Serializers for the magic system API.

This module provides serializers for both lookup tables (read-only)
and character-specific magic data.

Affinities and Resonances are proper domain models in the magic app.
"""

from rest_framework import serializers

from world.magic.constants import ALTERATION_TIER_CAPS
from world.magic.models import (
    Cantrip,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterFacet,
    CharacterGift,
    CharacterResonance,
    EffectType,
    Facet,
    Gift,
    MagicalAlterationTemplate,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
    PendingAlteration,
    Resonance,
    Restriction,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadJournal,
    ThreadResonance,
    ThreadType,
)

# =============================================================================
# Lookup Table Serializers (Read-Only)
# =============================================================================


class ResonanceSerializer(serializers.ModelSerializer):
    """Serializer for Resonance records."""

    affinity_name = serializers.CharField(source="affinity.name", read_only=True)
    codex_entry_id = serializers.SerializerMethodField()

    class Meta:
        model = Resonance
        fields = ["id", "name", "affinity", "affinity_name", "description", "codex_entry_id"]
        read_only_fields = fields

    def get_codex_entry_id(self, obj: Resonance) -> int | None:
        """Return the Codex entry ID if this resonance's modifier_target has one."""
        if (
            hasattr(obj, "modifier_target")
            and obj.modifier_target is not None
            and hasattr(obj.modifier_target, "codex_entry")
            and obj.modifier_target.codex_entry
        ):
            return obj.modifier_target.codex_entry.id
        return None


class ThreadTypeSerializer(serializers.ModelSerializer):
    """Serializer for ThreadType lookup records."""

    grants_resonance_name = serializers.CharField(
        source="grants_resonance.name",
        read_only=True,
        allow_null=True,
    )
    grants_resonance_detail = ResonanceSerializer(
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


class CantripFacetSerializer(serializers.ModelSerializer):
    """Lightweight facet representation for cantrip dropdown."""

    class Meta:
        model = Facet
        fields = ["id", "name"]
        read_only_fields = fields


class CantripSerializer(serializers.ModelSerializer):
    """Serializer for Cantrip lookup records with allowed facets.

    Mechanical fields (intensity, control, anima cost) are intentionally
    hidden — the player only sees name, description, archetype, and facets.
    style_id is exposed for path-based filtering.
    """

    allowed_facets = serializers.SerializerMethodField()
    style_id = serializers.PrimaryKeyRelatedField(source="style", read_only=True)

    class Meta:
        model = Cantrip
        fields = [
            "id",
            "name",
            "description",
            "archetype",
            "requires_facet",
            "facet_prompt",
            "allowed_facets",
            "sort_order",
            "style_id",
        ]
        read_only_fields = fields

    def get_allowed_facets(self, obj: Cantrip) -> list[dict]:
        """Get allowed facets using cached property."""
        return CantripFacetSerializer(obj.cached_allowed_facets, many=True).data


# =============================================================================
# Technique Serializers
# =============================================================================


class TechniqueSerializer(serializers.ModelSerializer):
    """Serializer for Technique records with intensity and control stats."""

    tier = serializers.IntegerField(read_only=True)
    restriction_ids = serializers.PrimaryKeyRelatedField(
        source="restrictions",
        many=True,
        queryset=Restriction.objects.all(),
        required=False,
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
            "intensity",
            "control",
            "anima_cost",
            "description",
            "source_cantrip",
            "tier",
        ]


# =============================================================================
# Gift Serializers
# =============================================================================


class GiftSerializer(serializers.ModelSerializer):
    """Serializer for Gift records with nested techniques."""

    affinity_breakdown = serializers.SerializerMethodField()
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
            "affinity_breakdown",
            "description",
            "resonances",
            "techniques",
            "technique_count",
        ]
        read_only_fields = fields

    def get_affinity_breakdown(self, obj) -> dict[str, int]:
        """Derive affinity from resonances' affiliated affinities."""
        return obj.get_affinity_breakdown()

    def get_resonances(self, obj) -> list[dict]:
        """Get resonances using cached property."""
        return ResonanceSerializer(obj.cached_resonances, many=True).data

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
        queryset=Resonance.objects.all(),
    )

    class Meta:
        model = Gift
        fields = ["id", "name", "resonance_ids", "description"]

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

    affinity_breakdown = serializers.SerializerMethodField()
    # Use annotated field from queryset (avoids N+1)
    technique_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Gift
        fields = [
            "id",
            "name",
            "affinity_breakdown",
            "description",
            "technique_count",
        ]
        read_only_fields = fields

    def get_affinity_breakdown(self, obj) -> dict[str, int]:
        """Derive affinity from resonances' affiliated affinities."""
        return obj.get_affinity_breakdown()


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
    resonance_detail = ResonanceSerializer(source="resonance", read_only=True)
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
    resonance_detail = ResonanceSerializer(source="resonance", read_only=True)

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
    resonance_detail = ResonanceSerializer(source="resonance", read_only=True)

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
    resonances = serializers.SerializerMethodField()

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

    def get_resonances(self, obj: Thread) -> list[dict]:
        """Get resonances using cached property."""
        return ThreadResonanceSerializer(obj.cached_resonances, many=True).data


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
# Facet Serializers
# =============================================================================


class FacetSerializer(serializers.ModelSerializer):
    """Serializer for Facet model with hierarchy info."""

    depth = serializers.IntegerField(read_only=True)
    full_path = serializers.CharField(read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)

    class Meta:
        model = Facet
        fields = ["id", "name", "parent", "parent_name", "description", "depth", "full_path"]
        read_only_fields = ["id", "depth", "full_path"]


class FacetTreeSerializer(serializers.ModelSerializer):
    """Serializer for Facet with nested children for tree display."""

    children = serializers.SerializerMethodField()

    class Meta:
        model = Facet
        fields = ["id", "name", "description", "children"]

    def get_children(self, obj) -> list[dict]:
        """Recursively serialize children."""
        children = obj.children.all()
        return FacetTreeSerializer(children, many=True).data


class CharacterFacetSerializer(serializers.ModelSerializer):
    """Serializer for CharacterFacet model."""

    facet_name = serializers.CharField(source="facet.name", read_only=True)
    facet_path = serializers.CharField(source="facet.full_path", read_only=True)
    resonance_name = serializers.CharField(source="resonance.name", read_only=True)

    class Meta:
        model = CharacterFacet
        fields = [
            "id",
            "character",
            "facet",
            "facet_name",
            "facet_path",
            "resonance",
            "resonance_name",
            "flavor_text",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


# =============================================================================
# Motif Serializers
# =============================================================================


class MotifResonanceAssociationSerializer(serializers.ModelSerializer):
    """Serializer for MotifResonanceAssociation records."""

    facet_name = serializers.CharField(source="facet.name", read_only=True)
    facet_path = serializers.CharField(source="facet.full_path", read_only=True)

    class Meta:
        model = MotifResonanceAssociation
        fields = ["id", "facet", "facet_name", "facet_path"]
        read_only_fields = ["id", "facet_name", "facet_path"]


class MotifResonanceSerializer(serializers.ModelSerializer):
    """Serializer for MotifResonance records with nested facet assignments."""

    resonance_name = serializers.CharField(source="resonance.name", read_only=True)
    facet_assignments = MotifResonanceAssociationSerializer(many=True, read_only=True)

    class Meta:
        model = MotifResonance
        fields = ["id", "resonance", "resonance_name", "is_from_gift", "facet_assignments"]
        read_only_fields = ["id", "resonance_name"]


class MotifSerializer(serializers.ModelSerializer):
    """Serializer for Motif records with nested resonances."""

    resonances = MotifResonanceSerializer(many=True, read_only=True)

    class Meta:
        model = Motif
        fields = ["id", "description", "resonances"]
        read_only_fields = ["id"]


# =============================================================================
# Alteration Serializers
# =============================================================================


class PendingAlterationSerializer(serializers.ModelSerializer):
    """Read-only serializer for pending alterations shown on character sheet."""

    origin_affinity_name = serializers.CharField(
        source="origin_affinity.name",
        read_only=True,
    )
    origin_resonance_name = serializers.CharField(
        source="origin_resonance.name",
        read_only=True,
    )
    tier_display = serializers.CharField(
        source="get_tier_display",
        read_only=True,
    )
    tier_caps = serializers.SerializerMethodField()

    class Meta:
        model = PendingAlteration
        fields = [
            "id",
            "status",
            "tier",
            "tier_display",
            "tier_caps",
            "origin_affinity_name",
            "origin_resonance_name",
            "triggering_scene",
            "created_at",
        ]

    def get_tier_caps(self, obj: PendingAlteration) -> dict:
        return ALTERATION_TIER_CAPS.get(obj.tier, {})


class LibraryEntrySerializer(serializers.ModelSerializer):
    """Read-only serializer for library browse cards."""

    name = serializers.CharField(
        source="condition_template.name",
        read_only=True,
    )
    player_description = serializers.CharField(
        source="condition_template.player_description",
        read_only=True,
    )
    observer_description = serializers.CharField(
        source="condition_template.observer_description",
        read_only=True,
    )
    origin_affinity_name = serializers.CharField(
        source="origin_affinity.name",
        read_only=True,
    )

    class Meta:
        model = MagicalAlterationTemplate
        fields = [
            "id",
            "name",
            "tier",
            "player_description",
            "observer_description",
            "origin_affinity_name",
            "weakness_magnitude",
            "resonance_bonus_magnitude",
            "social_reactivity_magnitude",
            "is_visible_at_rest",
        ]


class AlterationResolutionSerializer(serializers.Serializer):
    """Write serializer for resolving a PendingAlteration."""

    # Use-as-is path
    library_template_id = serializers.IntegerField(required=False)

    # Author-from-scratch path
    name = serializers.CharField(max_length=60, min_length=3, required=False)
    player_description = serializers.CharField(required=False)
    observer_description = serializers.CharField(required=False)
    weakness_damage_type_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    weakness_magnitude = serializers.IntegerField(
        min_value=0,
        default=0,
    )
    resonance_bonus_magnitude = serializers.IntegerField(
        min_value=0,
        default=0,
    )
    social_reactivity_magnitude = serializers.IntegerField(
        min_value=0,
        default=0,
    )
    is_visible_at_rest = serializers.BooleanField(default=False)
    parent_template_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        """Run tier schema validation against the pending's constraints."""
        from world.magic.services import validate_alteration_resolution  # noqa: PLC0415

        pending = self.context["pending"]
        is_staff = self.context["request"].user.is_staff

        # If library template, validate library entry exists and no duplicate
        if "library_template_id" in attrs:  # noqa: STRING_LITERAL — dict membership check, not an identifier
            library_errors = validate_alteration_resolution(
                pending_tier=pending.tier,
                pending_affinity_id=pending.origin_affinity_id,
                pending_resonance_id=pending.origin_resonance_id,
                payload={"library_entry_pk": attrs["library_template_id"]},
                is_staff=is_staff,
                character_sheet=self.context.get("character_sheet"),
            )
            if library_errors:
                raise serializers.ValidationError(library_errors)
            return attrs

        # Author-from-scratch: inject tier + origin from pending (not client-supplied)
        payload = {
            "tier": pending.tier,
            "origin_affinity_id": pending.origin_affinity_id,
            "origin_resonance_id": pending.origin_resonance_id,
            **attrs,
        }
        errors = validate_alteration_resolution(
            pending_tier=pending.tier,
            pending_affinity_id=pending.origin_affinity_id,
            pending_resonance_id=pending.origin_resonance_id,
            payload=payload,
            is_staff=is_staff,
            character_sheet=self.context.get("character_sheet"),
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

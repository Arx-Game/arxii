"""
Serializers for the magic system API.

This module provides serializers for both lookup tables (read-only)
and character-specific magic data.

Affinities and Resonances are proper domain models in the magic app.
"""

from rest_framework import serializers

from world.character_sheets.models import CharacterSheet
from world.conditions.models import DamageType
from world.items.models import ItemInstance
from world.magic.constants import ALTERATION_TIER_CAPS, TargetKind
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
    PoseEndorsement,
    Resonance,
    Restriction,
    Ritual,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadWeavingTeachingOffer,
)
from world.roster.models import RosterEntry

# Error messages — module constants keep tests stable and satisfy STRING_LITERAL.
_ERR_CHARACTER_SHEET_NOT_OWNED = "character_sheet_id does not belong to the requesting account."
_ERR_CHARACTER_SHEET_NOT_FOUND = "CharacterSheet not found."


def _resolve_account_sheet(sheet_id: int, request) -> CharacterSheet:
    """Resolve ``sheet_id`` to a CharacterSheet owned by ``request.user``.

    Staff bypass the ownership check. Raises ``serializers.ValidationError``
    on lookup miss or ownership violation.
    """
    try:
        sheet = CharacterSheet.objects.get(pk=sheet_id)
    except CharacterSheet.DoesNotExist as exc:
        raise serializers.ValidationError(_ERR_CHARACTER_SHEET_NOT_FOUND) from exc

    user = request.user if request is not None else None
    if user is not None and user.is_staff:
        return sheet

    if user is None:
        raise serializers.ValidationError(_ERR_CHARACTER_SHEET_NOT_OWNED)

    owned_ids = set(RosterEntry.objects.for_account(user).character_ids())
    if sheet.pk not in owned_ids:
        raise serializers.ValidationError(_ERR_CHARACTER_SHEET_NOT_OWNED)
    return sheet


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

    class Meta:
        model = CharacterResonance
        fields = [
            "id",
            "character_sheet",
            "resonance",
            "resonance_name",
            "resonance_detail",
            "balance",
            "lifetime_earned",
            "claimed_at",
            "flavor_text",
        ]
        read_only_fields = ["id", "claimed_at"]


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
    library_template_id = serializers.PrimaryKeyRelatedField(
        queryset=MagicalAlterationTemplate.objects.filter(is_library_entry=True),
        required=False,
        allow_null=True,
    )

    # Author-from-scratch path
    name = serializers.CharField(max_length=60, min_length=3, required=False)
    player_description = serializers.CharField(required=False)
    observer_description = serializers.CharField(required=False)
    weakness_damage_type_id = serializers.PrimaryKeyRelatedField(
        queryset=DamageType.objects.all(),
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
    parent_template_id = serializers.PrimaryKeyRelatedField(
        queryset=MagicalAlterationTemplate.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        """Run tier schema validation against the pending's constraints."""
        from world.magic.services import validate_alteration_resolution  # noqa: PLC0415

        pending = self.context["pending"]
        is_staff = self.context["request"].user.is_staff

        # If library template, validate library entry exists and no duplicate
        library_template = attrs.get("library_template_id")  # noqa: STRING_LITERAL — dict key matches field name
        if library_template is not None:
            library_errors = validate_alteration_resolution(
                pending_tier=pending.tier,
                pending_affinity_id=pending.origin_affinity_id,
                pending_resonance_id=pending.origin_resonance_id,
                payload={"library_entry_pk": library_template.pk},
                is_staff=is_staff,
                character_sheet=self.context.get("character_sheet"),
            )
            if library_errors:
                raise serializers.ValidationError(library_errors)
            return attrs

        # Author-from-scratch: inject tier + origin from pending (not client-supplied).
        # weakness_damage_type_id holds a DamageType instance after PrimaryKeyRelatedField
        # validation — the service checks this key for truthiness, so passing the instance
        # directly is safe.
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


# =============================================================================
# Resonance Pivot Spec A — Phase 16 API serializers (§4.5, §5.6)
# =============================================================================


class ThreadSerializer(serializers.ModelSerializer):
    """Serializer for Thread records (Spec A §4.5).

    Read: returns level / developed_points / resonance detail for display.
    Write: accepts target_kind + target_id + resonance + character_sheet_id to
    weave a new thread; target_id is resolved to the typed FK via ``create``
    which delegates to ``weave_thread``. ``character_sheet_id`` must identify
    a CharacterSheet on an active roster tenure belonging to the requesting
    account (staff may pass any sheet).
    """

    resonance_name = serializers.CharField(source="resonance.name", read_only=True)
    target_id = serializers.IntegerField(write_only=True, required=True)
    character_sheet_id = serializers.IntegerField(write_only=True, required=True)
    name = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = Thread
        fields = [
            "id",
            "owner",
            "resonance",
            "resonance_name",
            "target_kind",
            "target_id",
            "character_sheet_id",
            "name",
            "description",
            "level",
            "developed_points",
            "retired_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "level",
            "developed_points",
            "retired_at",
            "created_at",
            "updated_at",
        ]

    def validate_target_kind(self, value: str) -> str:
        """Ensure the discriminator is a valid TargetKind."""
        if value not in TargetKind.values:
            msg = f"Unknown target_kind: {value!r}."
            raise serializers.ValidationError(msg)
        return value

    def validate_character_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve + ownership-check the caller-supplied character_sheet_id."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate(self, attrs: dict) -> dict:
        """Resolve target_id → a target model instance matching target_kind."""
        target_kind = attrs.get("target_kind")
        target_id = attrs.get("target_id")
        if target_kind is None or target_id is None:
            return attrs
        attrs["_target"] = self._resolve_target(target_kind, target_id)
        return attrs

    @staticmethod
    def _resolve_target(target_kind: str, target_id: int) -> object:
        """Look up the target model instance for a given (target_kind, target_id)."""
        # In-function imports avoid app-boot circular deps (magic ↔ traits ↔ relationships).
        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        from world.magic.models import Technique as TechniqueModel  # noqa: PLC0415
        from world.relationships.models import (  # noqa: PLC0415
            RelationshipCapstone,
            RelationshipTrackProgress,
        )
        from world.traits.models import Trait  # noqa: PLC0415

        model_map: dict[str, type] = {
            TargetKind.TRAIT: Trait,
            TargetKind.TECHNIQUE: TechniqueModel,
            TargetKind.ITEM: ObjectDB,
            TargetKind.ROOM: ObjectDB,
            TargetKind.RELATIONSHIP_TRACK: RelationshipTrackProgress,
            TargetKind.RELATIONSHIP_CAPSTONE: RelationshipCapstone,
        }
        model = model_map.get(target_kind)
        if model is None:
            msg = f"Unsupported target_kind: {target_kind!r}."
            raise serializers.ValidationError(msg)
        try:
            return model.objects.get(pk=target_id)
        except model.DoesNotExist as exc:
            msg = f"{target_kind} target with id={target_id} does not exist."
            raise serializers.ValidationError(msg) from exc

    def create(self, validated_data: dict) -> Thread:
        """Delegate thread creation to ``weave_thread``."""
        from world.magic.exceptions import WeavingUnlockMissing  # noqa: PLC0415
        from world.magic.services import weave_thread  # noqa: PLC0415

        # character_sheet_id was replaced by the CharacterSheet instance in
        # validate_character_sheet_id — pop it before building kwargs.
        character_sheet = validated_data.pop("character_sheet_id")
        target = validated_data.pop("_target")
        validated_data.pop("target_id", None)

        try:
            return weave_thread(
                character_sheet=character_sheet,
                target_kind=validated_data["target_kind"],
                target=target,
                resonance=validated_data["resonance"],
                name=validated_data.get("name", ""),
                description=validated_data.get("description", ""),
            )
        except WeavingUnlockMissing as exc:
            raise serializers.ValidationError({"detail": exc.user_message}) from exc


class RitualSerializer(serializers.ModelSerializer):
    """Serializer for Ritual records (Spec A §4.5)."""

    class Meta:
        model = Ritual
        fields = [
            "id",
            "name",
            "description",
            "hedge_accessible",
            "glimpse_eligible",
            "narrative_prose",
            "execution_kind",
            "site_property",
        ]
        read_only_fields = fields


class ThreadWeavingTeachingOfferSerializer(serializers.ModelSerializer):
    """Serializer for ThreadWeavingTeachingOffer records (Spec A §4.5)."""

    unlock_target_kind = serializers.CharField(source="unlock.target_kind", read_only=True)
    unlock_display_name = serializers.CharField(source="unlock.display_name", read_only=True)
    unlock_xp_cost = serializers.IntegerField(source="unlock.xp_cost", read_only=True)

    class Meta:
        model = ThreadWeavingTeachingOffer
        fields = [
            "id",
            "teacher",
            "unlock",
            "unlock_target_kind",
            "unlock_display_name",
            "unlock_xp_cost",
            "pitch",
            "gold_cost",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Thread-pull preview (Spec A §5.6)
# ---------------------------------------------------------------------------


class PullActionContextSerializer(serializers.Serializer):
    """Wire shape for the optional ``action_context`` block in a pull preview.

    Only ``combat_encounter_id`` is consumed by the preview path — the rest
    of the fields are accepted for forward-compatibility with the eventual
    authoring UI (the pre-commit preview doesn't care about action_kind
    or anchors_in_play; the full commit path validates those).
    """

    action_kind = serializers.CharField(required=False, allow_blank=True)
    anchors_in_play = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )
    combat_encounter_id = serializers.IntegerField(required=False, allow_null=True)


class ThreadPullPreviewRequestSerializer(serializers.Serializer):
    """Request serializer for POST /api/magic/thread-pull-preview/.

    ``character_sheet_id`` is required and must identify a CharacterSheet the
    requesting account owns (staff may pass any sheet).
    """

    character_sheet_id = serializers.IntegerField(required=True)
    resonance_id = serializers.IntegerField(required=True)
    tier = serializers.IntegerField(required=True, min_value=1, max_value=3)
    thread_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )
    action_context = PullActionContextSerializer(required=False)

    def validate_character_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve + ownership-check the caller-supplied character_sheet_id."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)


class ResolvedPullEffectSerializer(serializers.Serializer):
    """Wire shape for a single ResolvedPullEffect row."""

    kind = serializers.CharField()
    authored_value = serializers.IntegerField(allow_null=True)
    level_multiplier = serializers.IntegerField()
    scaled_value = serializers.IntegerField()
    vital_target = serializers.CharField(allow_null=True)
    source_thread_id = serializers.SerializerMethodField()
    source_thread_level = serializers.IntegerField()
    source_tier = serializers.IntegerField()
    narrative_snippet = serializers.CharField()
    inactive = serializers.BooleanField()
    inactive_reason = serializers.CharField(allow_null=True)

    def get_source_thread_id(self, obj) -> int:
        """Expose the source thread's PK (the dataclass carries the Thread instance)."""
        return obj.source_thread.pk


class ThreadPullPreviewResponseSerializer(serializers.Serializer):
    """Response serializer for POST /api/magic/thread-pull-preview/."""

    resonance_cost = serializers.IntegerField()
    anima_cost = serializers.IntegerField()
    affordable = serializers.BooleanField()
    resolved_effects = ResolvedPullEffectSerializer(many=True)
    capped_intensity = serializers.BooleanField()


# ---------------------------------------------------------------------------
# Ritual perform (Spec A §4.5)
# ---------------------------------------------------------------------------


_SAFE_KWARG_TYPES: tuple[type, ...] = (int, str, bool)


class RitualPerformRequestSerializer(serializers.Serializer):
    """Request serializer for POST /api/magic/rituals/perform/.

    ``kwargs`` carries ritual-specific parameters forwarded to the dispatched
    service function or flow. To keep the surface safe we only accept
    primitive values (``int | str | bool | None``) — authored rituals are
    internally controlled and know how to resolve any model references from
    those primitive keys.
    """

    character_sheet_id = serializers.IntegerField(required=True)
    ritual_id = serializers.PrimaryKeyRelatedField(
        queryset=Ritual.objects.all(),
        required=True,
    )
    kwargs = serializers.DictField(
        child=serializers.JSONField(allow_null=True),
        required=False,
        default=dict,
    )
    components = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )

    def validate_character_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve + ownership-check the caller-supplied character_sheet_id."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate_kwargs(self, value: dict) -> dict:
        """Restrict kwargs values to primitive types (int | str | bool | None)."""
        for key, val in value.items():
            if not isinstance(key, str):
                msg = "Ritual kwargs keys must be strings."
                raise serializers.ValidationError(msg)
            if val is None:
                continue
            if not isinstance(val, _SAFE_KWARG_TYPES):
                msg = f"Ritual kwargs[{key!r}] must be a primitive (int, str, bool, or null)."
                raise serializers.ValidationError(msg)
        return value

    def validate_components(self, value: list[int]) -> list[ItemInstance]:
        """Resolve component PKs to ItemInstances; ownership checked in validate()."""
        if not value:
            return []
        instances = list(ItemInstance.objects.filter(pk__in=value).select_related("quality_tier"))
        found_pks = {inst.pk for inst in instances}
        missing = set(value) - found_pks
        if missing:
            msg = f"ItemInstance(s) not found: {sorted(missing)}."
            raise serializers.ValidationError(msg)
        return instances

    def validate(self, attrs: dict) -> dict:
        """Cross-field validation: ensure components belong to the acting sheet."""
        actor = attrs.get("character_sheet_id")
        instances = attrs.get("components") or []
        if actor is not None and instances:
            owner_account = actor.character.db_account_id
            for inst in instances:
                if inst.owner_id is not None and inst.owner_id != owner_account:
                    msg = f"ItemInstance {inst.pk} is not owned by the actor."
                    raise serializers.ValidationError(msg)
        return attrs


# =============================================================================
# Resonance Pivot Spec C — Pose Endorsement API serializer (Task 23)
# =============================================================================


class PoseEndorsementSerializer(serializers.ModelSerializer):
    """Serializer for PoseEndorsement create + read (Spec C Task 23).

    Write: accepts ``interaction`` + ``resonance`` PKs from the request body.
    The ``endorser_sheet`` is resolved from the requesting account in the
    view (``PoseEndorsementViewSet.perform_create``) and injected via
    ``serializer.save(endorser_sheet=sheet)``.

    Read: all fields are present; read-only fields cannot be supplied by the
    client.
    """

    class Meta:
        model = PoseEndorsement
        fields = [
            "id",
            "endorser_sheet",
            "endorsee_sheet",
            "interaction",
            "resonance",
            "persona_snapshot",
            "created_at",
            "settled_at",
            "granted_amount",
        ]
        read_only_fields = [
            "endorser_sheet",
            "endorsee_sheet",
            "persona_snapshot",
            "created_at",
            "settled_at",
            "granted_amount",
        ]

    def create(self, validated_data: dict) -> PoseEndorsement:
        """Delegate to ``create_pose_endorsement``; surface errors as 400."""
        from world.magic.exceptions import EndorsementValidationError  # noqa: PLC0415
        from world.magic.services.gain import create_pose_endorsement  # noqa: PLC0415

        endorser_sheet = validated_data.pop("endorser_sheet")
        interaction = validated_data["interaction"]
        resonance = validated_data["resonance"]
        try:
            return create_pose_endorsement(endorser_sheet, interaction, resonance)
        except EndorsementValidationError as exc:
            raise serializers.ValidationError({"detail": exc.user_message}) from exc

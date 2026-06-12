"""
Serializers for the magic system API.

This module provides serializers for both lookup tables (read-only)
and character-specific magic data.

Affinities and Resonances are proper domain models in the magic app.
"""

from typing import TYPE_CHECKING

from rest_framework import serializers

from world.character_sheets.models import CharacterSheet

if TYPE_CHECKING:
    from world.magic.audere import AudereThreshold
from world.conditions.models import CapabilityType, ConditionTemplate, DamageType
from world.items.models import ItemInstance
from world.magic.constants import ALTERATION_TIER_CAPS, TargetKind
from world.magic.models import (
    Cantrip,
    CharacterAnima,
    CharacterAura,
    CharacterGift,
    CharacterResonance,
    CharacterThreadWeavingUnlock,
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
    ResonanceGrant,
    Restriction,
    Ritual,
    SceneEntryEndorsement,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadLevelUnlock,
    ThreadWeavingTeachingOffer,
)
from world.magic.models.sessions import RitualSession
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

    character_id = serializers.IntegerField(source="character.pk", read_only=True)
    character_name = serializers.SerializerMethodField()
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
            "character_id",
            "character_name",
            "status",
            "tier",
            "tier_display",
            "tier_caps",
            "origin_affinity_name",
            "origin_resonance_name",
            "triggering_scene",
            "created_at",
        ]

    def get_character_name(self, obj: PendingAlteration) -> str:
        """Return the primary persona name for the pending's sheet."""
        persona = getattr(obj.character, "primary_persona", None)  # noqa: GETATTR_LITERAL
        return getattr(persona, "name", "") if persona is not None else ""  # noqa: GETATTR_LITERAL

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
        library_template = attrs.get("library_template_id")  # noqa: STRING_LITERAL
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


class AlterationResolutionResponseSerializer(serializers.Serializer):
    """Wire shape returned by the resolve action."""

    status = serializers.CharField()
    event_id = serializers.IntegerField()


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

    Read-only computed fields (SerializerMethodFields):
    - path_cap: the path-side cap (compute_path_cap)
    - anchor_cap: the anchor-side cap (compute_anchor_cap); null for ROOM threads
      (AnchorCapNotImplemented is not yet spec'd)
    - effective_cap: min(path_cap, anchor_cap); null when anchor_cap is null
    """

    resonance_name = serializers.CharField(source="resonance.name", read_only=True)
    target_id = serializers.IntegerField(write_only=True, required=True)
    character_sheet_id = serializers.IntegerField(write_only=True, required=True)
    name = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    path_cap = serializers.SerializerMethodField()
    anchor_cap = serializers.SerializerMethodField()
    effective_cap = serializers.SerializerMethodField()

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
            "path_cap",
            "anchor_cap",
            "effective_cap",
            "retired_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "level",
            "developed_points",
            "path_cap",
            "anchor_cap",
            "effective_cap",
            "retired_at",
            "created_at",
            "updated_at",
        ]

    def get_path_cap(self, obj: Thread) -> int:
        """Return the path-side cap for this thread's owner."""
        from world.magic.services.threads import compute_path_cap  # noqa: PLC0415

        return compute_path_cap(obj.owner)

    def get_anchor_cap(self, obj: Thread) -> int | None:
        """Return the anchor-side cap, or None for ROOM threads (not yet implemented)."""
        from world.magic.exceptions import AnchorCapNotImplemented  # noqa: PLC0415
        from world.magic.services.threads import compute_anchor_cap  # noqa: PLC0415

        try:
            return compute_anchor_cap(obj)
        except AnchorCapNotImplemented:
            return None

    def get_effective_cap(self, obj: Thread) -> int | None:
        """Return min(path_cap, anchor_cap), or None when anchor_cap is unavailable."""
        from world.magic.exceptions import AnchorCapNotImplemented  # noqa: PLC0415
        from world.magic.services.threads import (  # noqa: PLC0415
            compute_anchor_cap,
            compute_path_cap,
        )

        try:
            anchor = compute_anchor_cap(obj)
        except AnchorCapNotImplemented:
            return None
        return min(compute_path_cap(obj.owner), anchor)

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

        from world.covenants.models import CovenantRole  # noqa: PLC0415
        from world.magic.models import (  # noqa: PLC0415
            Facet,
            Technique as TechniqueModel,
        )
        from world.relationships.models import (  # noqa: PLC0415
            RelationshipCapstone,
            RelationshipTrackProgress,
        )
        from world.traits.models import Trait  # noqa: PLC0415

        model_map: dict[str, type] = {
            TargetKind.TRAIT: Trait,
            TargetKind.TECHNIQUE: TechniqueModel,
            TargetKind.ROOM: ObjectDB,
            TargetKind.RELATIONSHIP_TRACK: RelationshipTrackProgress,
            TargetKind.RELATIONSHIP_CAPSTONE: RelationshipCapstone,
            TargetKind.FACET: Facet,
            TargetKind.COVENANT_ROLE: CovenantRole,
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

        from world.covenants.exceptions import CovenantRoleNeverHeldError  # noqa: PLC0415

        try:
            return weave_thread(
                character_sheet=character_sheet,
                target_kind=validated_data["target_kind"],
                target=target,
                resonance=validated_data["resonance"],
                name=validated_data.get("name", ""),
                description=validated_data.get("description", ""),
            )
        except (WeavingUnlockMissing, CovenantRoleNeverHeldError) as exc:
            raise serializers.ValidationError({"detail": exc.user_message}) from exc


class RitualSceneActionConfigSerializer(serializers.ModelSerializer):
    """Nested read-only serializer for RitualSceneActionConfig sidecars.

    Exposes the check specification for SCENE_ACTION rituals so the frontend
    detail panel can display stat/skill/check_type information.
    """

    stat_name = serializers.CharField(source="stat.name", read_only=True)
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    specialization_id = serializers.PrimaryKeyRelatedField(source="specialization", read_only=True)
    resonance_id = serializers.PrimaryKeyRelatedField(source="resonance", read_only=True)
    check_type_id = serializers.PrimaryKeyRelatedField(source="check_type", read_only=True)
    check_type_name = serializers.SerializerMethodField()

    class Meta:
        from world.magic.models.ritual_scene_action import (  # noqa: PLC0415
            RitualSceneActionConfig,
        )

        model = RitualSceneActionConfig
        fields = [
            "id",
            "stat",
            "stat_name",
            "skill",
            "skill_name",
            "specialization_id",
            "resonance_id",
            "check_type_id",
            "check_type_name",
            "target_difficulty",
        ]
        read_only_fields = fields

    def get_check_type_name(self, obj) -> str | None:
        """Return the name of the check type, or None if not set."""
        if obj.check_type_id is None:
            return None
        return obj.check_type.name


class RitualSerializer(serializers.ModelSerializer):
    """Serializer for Ritual (read-only list/detail).

    Exposes name, description, narrative_prose, dispatch metadata, the
    `input_schema` blob the frontend uses to render its perform form,
    `author_account_id` for client-side "authored by you" filtering,
    and the nested `scene_action_config` for SCENE_ACTION rituals.
    """

    author_account_id = serializers.PrimaryKeyRelatedField(
        source="author_account", read_only=True, allow_null=True
    )
    scene_action_config = serializers.SerializerMethodField()

    class Meta:
        model = Ritual
        fields = [
            "id",
            "name",
            "description",
            "narrative_prose",
            "hedge_accessible",
            "glimpse_eligible",
            "execution_kind",
            "input_schema",
            "author_account_id",
            "scene_action_config",
            "client_hosted",
            "participation_rule",
            "min_participants",
            "max_participants",
        ]
        read_only_fields = fields

    def get_scene_action_config(self, obj: Ritual) -> dict | None:
        """Return nested scene_action_config for SCENE_ACTION rituals, else None."""
        from world.magic.constants import RitualExecutionKind  # noqa: PLC0415

        if obj.execution_kind != RitualExecutionKind.SCENE_ACTION:
            return None
        try:
            config = obj.scene_action_config
        except Exception:  # noqa: BLE001
            return None
        return RitualSceneActionConfigSerializer(config).data


class RitualSceneActionConfigPatchSerializer(serializers.Serializer):
    """Write serializer for the nested scene_action_config on a PATCH.

    Only fields that players can meaningfully update are included.
    All are optional (partial update semantics). FK fields accept integer PKs
    and are resolved to model instances in validate().
    """

    stat_id = serializers.IntegerField(required=False)
    skill_id = serializers.IntegerField(required=False)
    specialization_id = serializers.IntegerField(required=False, allow_null=True)
    resonance_id = serializers.IntegerField(required=False, allow_null=True)
    check_type_id = serializers.IntegerField(required=False, allow_null=True)
    target_difficulty = serializers.IntegerField(min_value=1, required=False)

    @staticmethod
    def _resolve_nullable_fk(
        attrs: dict,
        key: str,
        model: type,
        field_name: str,
        resolved: dict,
    ) -> None:
        """Resolve an optional nullable FK id to its model instance.

        Writes the resolved instance (or None) into *resolved[field_name]*.
        Raises ``ValidationError`` when the PK is non-null but not found.
        """
        if key not in attrs:
            return
        pk = attrs[key]
        if pk is None:
            resolved[field_name] = None
            return
        try:
            resolved[field_name] = model.objects.get(pk=pk)
        except model.DoesNotExist as exc:
            raise serializers.ValidationError({key: f"{model.__name__} not found."}) from exc

    def validate(self, attrs: dict) -> dict:
        """Resolve integer PK fields to model instances."""
        from world.checks.models import CheckType  # noqa: PLC0415
        from world.skills.models import Skill, Specialization  # noqa: PLC0415
        from world.traits.models import Trait, TraitType  # noqa: PLC0415

        resolved: dict = {}

        # Required (non-nullable) FK fields — only resolve if provided.
        if (val := attrs.get("stat_id")) is not None:
            try:
                resolved["stat"] = Trait.objects.get(pk=val, trait_type=TraitType.STAT)
            except Trait.DoesNotExist as exc:
                raise serializers.ValidationError({"stat_id": "Stat trait not found."}) from exc
        if (val := attrs.get("skill_id")) is not None:
            try:
                resolved["skill"] = Skill.objects.get(pk=val)
            except Skill.DoesNotExist as exc:
                raise serializers.ValidationError({"skill_id": "Skill not found."}) from exc

        # Nullable FK fields — resolve via helper.
        self._resolve_nullable_fk(
            attrs, "specialization_id", Specialization, "specialization", resolved
        )
        self._resolve_nullable_fk(attrs, "resonance_id", Resonance, "resonance", resolved)
        self._resolve_nullable_fk(attrs, "check_type_id", CheckType, "check_type", resolved)

        if "target_difficulty" in attrs:  # noqa: STRING_LITERAL
            resolved["target_difficulty"] = attrs["target_difficulty"]
        return resolved


class RitualPatchSerializer(serializers.ModelSerializer):
    """Write serializer for partial PATCH of player-authored Rituals.

    Handles top-level Ritual fields (name, description, narrative_prose) and
    optional nested ``scene_action_config`` for SCENE_ACTION rituals. Non-SCENE_ACTION
    rituals silently ignore scene_action_config if supplied.
    """

    scene_action_config = RitualSceneActionConfigPatchSerializer(required=False)

    class Meta:
        model = Ritual
        fields = ["name", "description", "narrative_prose", "scene_action_config"]

    def update(self, instance: Ritual, validated_data: dict) -> Ritual:
        """Update top-level fields then optionally update the sidecar."""
        from world.magic.constants import RitualExecutionKind  # noqa: PLC0415

        config_data = validated_data.pop("scene_action_config", None)
        ritual = super().update(instance, validated_data)
        if config_data and instance.execution_kind == RitualExecutionKind.SCENE_ACTION:
            try:
                config = instance.scene_action_config
            except Exception:  # noqa: BLE001
                return ritual
            for field, value in config_data.items():
                setattr(config, field, value)
            config.save()
        return ritual


class ThreadWeavingTeachingOfferSerializer(serializers.ModelSerializer):
    """Serializer for ThreadWeavingTeachingOffer records (Spec A §4.5)."""

    unlock_target_kind = serializers.CharField(source="unlock.target_kind", read_only=True)
    unlock_display_name = serializers.CharField(source="unlock.display_name", read_only=True)
    unlock_xp_cost = serializers.IntegerField(source="unlock.xp_cost", read_only=True)
    # Anonymity-respecting display from RosterTenure.display_name — e.g. "2nd
    # player of Ariel". Replaces the raw teacher PK in the UI (#540). Path:
    # teacher (RosterTenure) → roster_entry → character_sheet → character.
    # ViewSet's select_related extends through this chain to avoid N+1.
    teacher_display_name = serializers.CharField(source="teacher.display_name", read_only=True)
    effective_xp_cost_for_viewer = serializers.SerializerMethodField()

    class Meta:
        model = ThreadWeavingTeachingOffer
        fields = [
            "id",
            "teacher",
            "teacher_display_name",
            "unlock",
            "unlock_target_kind",
            "unlock_display_name",
            "unlock_xp_cost",
            "effective_xp_cost_for_viewer",
            "pitch",
            "gold_cost",
        ]
        read_only_fields = fields

    def _get_viewer_sheets(self, request) -> list:
        """Return the viewer's active CharacterSheets, cached on the request object.

        Called once per list response — caches the result on ``request`` so that
        N rows do not trigger N tenant-resolution queries.
        """
        cache_attr = "_cached_viewer_sheets"  # noqa: STRING_LITERAL
        if not hasattr(request, cache_attr):
            setattr(
                request,
                cache_attr,
                list(
                    CharacterSheet.objects.filter(
                        roster_entry__tenures__player_data__account=request.user,
                        roster_entry__tenures__end_date__isnull=True,
                    )
                ),
            )
        return getattr(request, cache_attr)

    def get_effective_xp_cost_for_viewer(self, obj: ThreadWeavingTeachingOffer) -> int | None:
        """Compute the Path-multiplied XP cost for the requesting learner.

        Returns the integer cost when the viewer has exactly one active tenure
        OR provides a ``learner_sheet_id`` query param to disambiguate.
        Returns ``None`` for ambiguous (multi-tenure, no key) or no-tenure cases.

        Uses ``_get_viewer_sheets`` so the tenant-resolution query fires only once
        per list response, not once per row.
        """
        from world.magic.services.threads import compute_thread_weaving_xp_cost  # noqa: PLC0415

        request = self.context.get("request")
        if request is None:
            return None

        sheets = self._get_viewer_sheets(request)
        if not sheets:
            return None
        if len(sheets) == 1:
            learner = sheets[0]
        else:
            # Multi-tenure: require explicit learner_sheet_id query param.
            requested_pk = request.query_params.get(  # noqa: STRING_LITERAL
                "learner_sheet_id"
            )
            if requested_pk is None:
                return None
            try:
                learner = next(s for s in sheets if s.pk == int(requested_pk))
            except (StopIteration, ValueError):
                return None

        return compute_thread_weaving_xp_cost(obj.unlock, learner)


class AcceptTeachingOfferSerializer(serializers.Serializer):
    """Serializer for accepting a ThreadWeavingTeachingOffer (Spec A §6.1).

    Optional ``learner_sheet_id`` disambiguates the learner when the requesting
    account has multiple active tenures (alt-guard).  The view provides the
    offer instance via serializer context as ``"offer"``.
    """

    learner_sheet_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:  # type: ignore[override]
        """Resolve the learner sheet using the alt-guard helper."""
        from world.magic.services.auth import _resolve_actor_sheet  # noqa: PLC0415

        request = self.context["request"]
        learner = _resolve_actor_sheet(request, body_key="learner_sheet_id")  # noqa: STRING_LITERAL
        attrs["learner"] = learner
        return attrs

    def create(self, validated_data: dict) -> CharacterThreadWeavingUnlock:  # type: ignore[override]
        """Call accept_thread_weaving_unlock; catch XPInsufficient → ValidationError."""
        from world.magic.exceptions import XPInsufficient  # noqa: PLC0415
        from world.magic.services.threads import accept_thread_weaving_unlock  # noqa: PLC0415

        learner = validated_data["learner"]
        offer = self.context["offer"]
        try:
            return accept_thread_weaving_unlock(learner, offer)
        except XPInsufficient as exc:
            raise serializers.ValidationError(exc.user_message) from exc


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


# =============================================================================
# Resonance Pivot Spec C — Scene Entry Endorsement API serializer (Task 24)
# =============================================================================


class SceneEntryEndorsementSerializer(serializers.ModelSerializer):
    """Serializer for SceneEntryEndorsement create + read (Spec C Task 24).

    Write: accepts ``endorsee_sheet`` + ``scene`` + ``resonance`` PKs from the
    request body. The ``endorser_sheet`` is resolved from the requesting account
    in the view (``SceneEntryEndorsementViewSet.perform_create``) and injected
    via ``serializer.save(endorser_sheet=sheet)``.

    No DELETE — scene-entry endorsements are immutable at creation (grant fires
    immediately). Reversal is deferred to the ResonanceGrantReversal PR.
    """

    class Meta:
        model = SceneEntryEndorsement
        fields = [
            "id",
            "endorser_sheet",
            "endorsee_sheet",
            "scene",
            "entry_interaction",
            "resonance",
            "persona_snapshot",
            "granted_amount",
            "created_at",
        ]
        read_only_fields = [
            "endorser_sheet",
            "entry_interaction",
            "persona_snapshot",
            "granted_amount",
            "created_at",
        ]

    def create(self, validated_data: dict) -> SceneEntryEndorsement:
        """Delegate to ``create_scene_entry_endorsement``; surface errors as 400."""
        from world.magic.exceptions import EndorsementValidationError  # noqa: PLC0415
        from world.magic.services.gain import create_scene_entry_endorsement  # noqa: PLC0415

        endorser_sheet = validated_data.pop("endorser_sheet")
        endorsee_sheet = validated_data["endorsee_sheet"]
        scene = validated_data["scene"]
        resonance = validated_data["resonance"]
        try:
            return create_scene_entry_endorsement(endorser_sheet, endorsee_sheet, scene, resonance)
        except EndorsementValidationError as exc:
            raise serializers.ValidationError({"detail": exc.user_message}) from exc


# =============================================================================
# Resonance Pivot Spec C — ResonanceGrant read-only ledger (Task 25)
# =============================================================================


class ResonanceGrantSerializer(serializers.ModelSerializer):
    """Read-only serializer for ResonanceGrant audit ledger rows (Spec C Task 25)."""

    class Meta:
        model = ResonanceGrant
        fields = [
            "id",
            "character_sheet",
            "resonance",
            "amount",
            "source",
            "granted_at",
            "source_room_profile",
            "source_staff_account",
            "source_pose_endorsement",
            "source_scene_entry_endorsement",
        ]
        read_only_fields = fields


# =============================================================================
# Resonance Pivot Spec B — Soul Tether API serializers (Phase 11)
# =============================================================================

# Error messages — module constants keep tests stable and satisfy STRING_LITERAL.
_ERR_SOUL_TETHER_NOT_FOUND = "Soul Tether relationship not found."
_ERR_RESONANCE_NOT_FOUND = "Resonance not found."
_ERR_SELF_TETHER = "Cannot form a Soul Tether with yourself."
_ERR_WRITEUP_TOO_SHORT = "Writeup must be at least 20 characters."
_ERR_MAX_UNITS_POSITIVE = "max_units must be a positive integer."
_ERR_UNITS_ACCEPTED_NON_NEGATIVE = "units_accepted must be zero or greater."
_ERR_SCENE_NOT_FOUND = "Scene not found."


class AcceptSoulTetherSerializer(serializers.Serializer):
    """Write serializer for forming a Soul Tether (Spec B §12).

    ``actor_sheet_id`` identifies the character sheet of the requesting account.
    ``partner_sheet_id`` identifies the partner's character sheet.
    ``sinner_role`` determines which side (SINNER or SINEATER) the initiator holds.
    ``resonance_id`` selects the resonance for the Sinner's Thread.
    ``writeup`` is the narrative description of the bond (20+ chars).
    """

    actor_sheet_id = serializers.IntegerField()
    partner_sheet_id = serializers.IntegerField()
    sinner_role = serializers.ChoiceField(choices=["SINNER", "SINEATER"])
    resonance_id = serializers.IntegerField()
    writeup = serializers.CharField(min_length=20, max_length=4000)

    def validate_actor_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve actor sheet with ownership check."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate_partner_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve partner sheet (ownership NOT required — it's the other party)."""
        try:
            return CharacterSheet.objects.get(pk=value)
        except CharacterSheet.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_CHARACTER_SHEET_NOT_FOUND) from exc

    def validate_resonance_id(self, value: int) -> "Resonance":
        """Resolve resonance by PK."""
        try:
            return Resonance.objects.get(pk=value)
        except Resonance.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_RESONANCE_NOT_FOUND) from exc

    def validate(self, attrs: dict) -> dict:
        """Cross-field: actor cannot tether with themselves."""
        actor = attrs.get("actor_sheet_id")
        partner = attrs.get("partner_sheet_id")
        if actor is not None and partner is not None and actor.pk == partner.pk:
            raise serializers.ValidationError(_ERR_SELF_TETHER)
        return attrs

    def create(self, validated_data: dict) -> object:
        """Delegate to accept_soul_tether; surface typed errors as 400."""
        from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
        from world.magic.services.soul_tether import accept_soul_tether  # noqa: PLC0415
        from world.magic.types.soul_tether import SoulTetherRole  # noqa: PLC0415

        actor_sheet: CharacterSheet = validated_data["actor_sheet_id"]
        partner_sheet: CharacterSheet = validated_data["partner_sheet_id"]
        sinner_role = SoulTetherRole(validated_data["sinner_role"])
        resonance: Resonance = validated_data["resonance_id"]
        writeup: str = validated_data["writeup"]
        try:
            return accept_soul_tether(
                initiator_sheet=actor_sheet,
                partner_sheet=partner_sheet,
                sinner_role=sinner_role,
                resonance=resonance,
                writeup=writeup,
                ritual_components=[],
            )
        except SoulTetherError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class SoulTetherDetailSerializer(serializers.Serializer):
    """Read serializer for GET /api/magic/soul-tether/{relationship_id}/.

    Returns tether state: Hollow current/max, Thread levels, Sineater stats,
    and role information. Accepts a CharacterRelationship (either direction).
    """

    relationship_id = serializers.IntegerField(read_only=True, source="pk")
    is_soul_tether = serializers.BooleanField(read_only=True)
    soul_tether_role = serializers.CharField(read_only=True)

    # Derived state via SerializerMethodField
    sinner_sheet_id = serializers.SerializerMethodField()
    sineater_sheet_id = serializers.SerializerMethodField()
    hollow_current = serializers.SerializerMethodField()
    hollow_max = serializers.SerializerMethodField()
    sineater_lifetime_helped = serializers.SerializerMethodField()
    sinner_corruption_stage = serializers.SerializerMethodField()
    sineater_strain_stage = serializers.SerializerMethodField()

    def _resolve_directions(self, obj: object) -> tuple[object, object]:
        """Return (sinner_relationship, sineater_relationship) for this tether.

        Handles either direction being passed as ``obj``.
        """
        from world.magic.constants import SoulTetherRole  # noqa: PLC0415
        from world.relationships.models import CharacterRelationship  # noqa: PLC0415

        if obj.soul_tether_role == SoulTetherRole.SINNER:  # type: ignore[union-attr]
            outgoing = obj
            incoming = CharacterRelationship.objects.filter(
                source=obj.target,  # type: ignore[union-attr]
                target=obj.source,  # type: ignore[union-attr]
                is_soul_tether=True,
            ).first()
        else:
            incoming = obj
            outgoing = CharacterRelationship.objects.filter(
                source=obj.target,  # type: ignore[union-attr]
                target=obj.source,  # type: ignore[union-attr]
                is_soul_tether=True,
            ).first()
        return outgoing, incoming

    def get_sinner_sheet_id(self, obj: object) -> int | None:
        """Return the Sinner's CharacterSheet PK."""
        outgoing, _ = self._resolve_directions(obj)
        if outgoing is None:
            return None
        return outgoing.source_id  # type: ignore[union-attr]

    def get_sineater_sheet_id(self, obj: object) -> int | None:
        """Return the Sineater's CharacterSheet PK."""
        outgoing, _ = self._resolve_directions(obj)
        if outgoing is None:
            return None
        return outgoing.target_id  # type: ignore[union-attr]

    def get_hollow_current(self, obj: object) -> int:
        """Return the Sinner's current Hollow capacity (from the capstone Thread)."""
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models import Thread  # noqa: PLC0415

        outgoing, _ = self._resolve_directions(obj)
        if outgoing is None:
            return 0
        sinner_sheet = outgoing.source  # type: ignore[union-attr]
        capstone = outgoing.capstones.filter(is_ritual_capstone=True).first()  # type: ignore[union-attr]
        if capstone is None:
            return 0
        thread = Thread.objects.filter(
            owner=sinner_sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=capstone,
            retired_at__isnull=True,
        ).first()
        return thread.hollow_current if thread is not None else 0

    def get_hollow_max(self, obj: object) -> int:
        """Return the Sinner's Hollow maximum (thread.level * 10)."""
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models import Thread  # noqa: PLC0415

        outgoing, _ = self._resolve_directions(obj)
        if outgoing is None:
            return 0
        sinner_sheet = outgoing.source  # type: ignore[union-attr]
        capstone = outgoing.capstones.filter(is_ritual_capstone=True).first()  # type: ignore[union-attr]
        if capstone is None:
            return 0
        thread = Thread.objects.filter(
            owner=sinner_sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=capstone,
            retired_at__isnull=True,
        ).first()
        return thread.level * 10 if thread is not None else 0

    def get_sineater_lifetime_helped(self, obj: object) -> int:
        """Return the Sineater's total lifetime_helped across all resonances for this bond."""
        from world.magic.models import CharacterResonance  # noqa: PLC0415

        outgoing, _ = self._resolve_directions(obj)
        if outgoing is None:
            return 0
        sineater_sheet = outgoing.target  # type: ignore[union-attr]
        result = CharacterResonance.objects.filter(
            character_sheet=sineater_sheet,
        ).values_list("lifetime_helped", flat=True)
        return sum(result)

    def get_sinner_corruption_stage(self, obj: object) -> int:
        """Return the Sinner's highest corruption stage across all resonances."""
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        outgoing, _ = self._resolve_directions(obj)
        if outgoing is None:
            return 0
        sinner_sheet = outgoing.source  # type: ignore[union-attr]
        # Find highest stage_order among all active Corruption ConditionInstances
        instances = ConditionInstance.objects.filter(
            target=sinner_sheet.character,
            condition__corruption_resonance__isnull=False,
        ).select_related("current_stage")
        stages = [
            inst.current_stage.stage_order for inst in instances if inst.current_stage is not None
        ]
        return max(stages) if stages else 0

    def get_sineater_strain_stage(self, obj: object) -> int:
        """Return the Sineater's current Tether Strain severity (or 0 if none)."""
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        _, incoming = self._resolve_directions(obj)
        if incoming is None:
            return 0
        sineater_sheet = incoming.source  # type: ignore[union-attr]
        strain = ConditionInstance.objects.filter(
            target=sineater_sheet.character,
            condition__name="Tether Strain",
        ).first()
        return strain.severity if strain is not None else 0


class SineatingRequestSerializer(serializers.Serializer):
    """Write serializer for Sinner-initiated Sineating request (Spec B §7).

    Returns a ``SineatingOffer`` that the Sineater can accept or decline via
    the respond endpoint.
    """

    actor_sheet_id = serializers.IntegerField()
    sineater_sheet_id = serializers.IntegerField()
    resonance_id = serializers.IntegerField()
    max_units = serializers.IntegerField(min_value=1)
    scene_id = serializers.IntegerField()

    def validate_actor_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve Sinner sheet with ownership check."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate_sineater_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve Sineater sheet."""
        try:
            return CharacterSheet.objects.get(pk=value)
        except CharacterSheet.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_CHARACTER_SHEET_NOT_FOUND) from exc

    def validate_resonance_id(self, value: int) -> "Resonance":
        """Resolve resonance by PK."""
        try:
            return Resonance.objects.get(pk=value)
        except Resonance.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_RESONANCE_NOT_FOUND) from exc

    def validate_scene_id(self, value: int) -> object:
        """Resolve scene by PK."""
        from world.scenes.models import Scene  # noqa: PLC0415

        try:
            return Scene.objects.get(pk=value)
        except Scene.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_SCENE_NOT_FOUND) from exc

    def create(self, validated_data: dict) -> object:
        """Delegate to request_sineating; surface typed errors as 400."""
        from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
        from world.magic.services.soul_tether import request_sineating  # noqa: PLC0415

        try:
            return request_sineating(
                sinner_sheet=validated_data["actor_sheet_id"],
                sineater_sheet=validated_data["sineater_sheet_id"],
                resonance=validated_data["resonance_id"],
                max_units=validated_data["max_units"],
                scene=validated_data["scene_id"],
            )
        except SoulTetherError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class SineatingOfferSerializer(serializers.Serializer):
    """Read serializer for SineatingOffer payloads returned by the request endpoint."""

    sinner_sheet_id = serializers.SerializerMethodField()
    sineater_sheet_id = serializers.SerializerMethodField()
    resonance_id = serializers.SerializerMethodField()
    max_units_offered = serializers.IntegerField()
    anima_cost_per_unit = serializers.IntegerField()
    fatigue_cost_per_unit = serializers.IntegerField()
    current_hollow = serializers.IntegerField()
    hollow_max = serializers.IntegerField()
    sineater_current_strain_stage = serializers.IntegerField()

    def get_sinner_sheet_id(self, obj: object) -> int:
        """Return sinner_sheet PK."""
        return obj.sinner_sheet.pk  # type: ignore[union-attr]

    def get_sineater_sheet_id(self, obj: object) -> int:
        """Return sineater_sheet PK."""
        return obj.sineater_sheet.pk  # type: ignore[union-attr]

    def get_resonance_id(self, obj: object) -> int:
        """Return resonance PK."""
        return obj.resonance.pk  # type: ignore[union-attr]


class SineatingRespondSerializer(serializers.Serializer):
    """Write serializer for the Sineater's response to a Sineating request (Spec B §7).

    The pending offer row is the canonical source of truth for scene, resonance,
    and units cap — the caller only needs to identify the pair and supply their choice.
    ``units_accepted=0`` means decline.
    """

    sinner_sheet_id = serializers.IntegerField()
    sineater_sheet_id = serializers.IntegerField()
    units_accepted = serializers.IntegerField(min_value=0)

    def validate_sineater_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve + ownership-check: caller must be the Sineater."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate_sinner_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve sinner sheet."""
        try:
            return CharacterSheet.objects.get(pk=value)
        except CharacterSheet.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_CHARACTER_SHEET_NOT_FOUND) from exc

    def create(self, validated_data: dict) -> object:
        """Resolve Sineating from the persisted pending offer; surface typed errors as 400.

        Delegates to ``resolve_sineating_from_db`` which looks up the pending
        offer row, validates co-location, executes resolution, and deletes the row.
        The serializer no longer re-runs ``request_sineating`` — the pending row
        is the canonical offer state.
        """
        from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
        from world.magic.services.soul_tether import resolve_sineating_from_db  # noqa: PLC0415

        try:
            return resolve_sineating_from_db(
                sinner_sheet=validated_data["sinner_sheet_id"],
                sineater_sheet=validated_data["sineater_sheet_id"],
                units_accepted=validated_data["units_accepted"],
            )
        except SoulTetherError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class SineatingResultSerializer(serializers.Serializer):
    """Read serializer for SineatingResult payloads."""

    units_accepted = serializers.IntegerField()
    declined = serializers.BooleanField()
    new_hollow_current = serializers.IntegerField()
    new_lifetime_helped = serializers.IntegerField()
    audit_row_id = serializers.SerializerMethodField()

    def get_audit_row_id(self, obj: object) -> int:
        """Return the audit Sineating row PK."""
        return obj.audit_row.pk  # type: ignore[union-attr]


class SoulTetherRescueSerializer(serializers.Serializer):
    """Write serializer for the rescue ritual (Spec B §9).

    The Sineater performs the ritual on the Sinner. Both must be in the same scene.
    """

    actor_sheet_id = serializers.IntegerField()
    sinner_sheet_id = serializers.IntegerField()
    resonance_id = serializers.IntegerField()
    scene_id = serializers.IntegerField()

    def validate_actor_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve Sineater sheet with ownership check."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate_sinner_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve Sinner sheet."""
        try:
            return CharacterSheet.objects.get(pk=value)
        except CharacterSheet.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_CHARACTER_SHEET_NOT_FOUND) from exc

    def validate_resonance_id(self, value: int) -> "Resonance":
        """Resolve resonance by PK."""
        try:
            return Resonance.objects.get(pk=value)
        except Resonance.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_RESONANCE_NOT_FOUND) from exc

    def validate_scene_id(self, value: int) -> object:
        """Resolve scene by PK."""
        from world.scenes.models import Scene  # noqa: PLC0415

        try:
            return Scene.objects.get(pk=value)
        except Scene.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_SCENE_NOT_FOUND) from exc

    def create(self, validated_data: dict) -> object:
        """Delegate to perform_soul_tether_rescue; surface typed errors as 400."""
        from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
        from world.magic.services.soul_tether import perform_soul_tether_rescue  # noqa: PLC0415

        try:
            return perform_soul_tether_rescue(
                sineater_sheet=validated_data["actor_sheet_id"],
                sinner_sheet=validated_data["sinner_sheet_id"],
                resonance=validated_data["resonance_id"],
                components=[],
                scene=validated_data["scene_id"],
            )
        except SoulTetherError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class RescueOutcomeSerializer(serializers.Serializer):
    """Read serializer for RescueOutcome payloads."""

    severity_reduced = serializers.IntegerField()
    sinner_stage_at_start = serializers.IntegerField()
    sinner_stage_at_end = serializers.IntegerField()
    sineater_strain_taken = serializers.IntegerField()
    protagonism_lock_lifted = serializers.BooleanField()
    audit_row_id = serializers.SerializerMethodField()

    def get_audit_row_id(self, obj: object) -> int:
        """Return the SoulTetherRescue audit row PK."""
        return obj.audit_row.pk  # type: ignore[union-attr]


class DissolveSerializer(serializers.Serializer):
    """Write serializer for dissolving a Soul Tether (Spec B §13).

    Either party may dissolve; ``actor_sheet_id`` is validated for ownership.
    ``relationship_id`` is the PK of *either* directional CharacterRelationship row.
    """

    actor_sheet_id = serializers.IntegerField()
    relationship_id = serializers.IntegerField()

    def validate_actor_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve actor sheet with ownership check."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate_relationship_id(self, value: int) -> object:
        """Resolve the CharacterRelationship, verifying it is an active Soul Tether."""
        from world.relationships.models import CharacterRelationship  # noqa: PLC0415

        try:
            rel = CharacterRelationship.objects.get(pk=value)
        except CharacterRelationship.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_SOUL_TETHER_NOT_FOUND) from exc
        if not rel.is_soul_tether:
            raise serializers.ValidationError(_ERR_SOUL_TETHER_NOT_FOUND)
        return rel

    def create(self, validated_data: dict) -> object:
        """Delegate to dissolve_soul_tether; surface typed errors as 400.

        Returns the relationship object post-dissolution as the DRF ``create()``
        contract requires a non-None return value from non-ModelSerializer.create().
        """
        from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
        from world.magic.services.soul_tether import dissolve_soul_tether  # noqa: PLC0415

        relationship = validated_data["relationship_id"]
        actor_sheet: CharacterSheet = validated_data["actor_sheet_id"]
        try:
            dissolve_soul_tether(
                relationship_id=relationship.pk,
                initiator_sheet=actor_sheet,
            )
        except SoulTetherError as exc:
            raise serializers.ValidationError(exc.user_message) from exc
        return relationship


class SineatingPendingOfferSerializer(serializers.ModelSerializer):
    """Sineater-facing view of a pending Sineating offer (inbox UI).

    Read-only. Scoped to the authenticated user's character sheets as Sineater.
    """

    sinner_persona_name = serializers.SerializerMethodField()
    sinner_sheet_id = serializers.IntegerField(read_only=True)
    scene_name = serializers.CharField(source="scene.name", read_only=True)
    resonance_id = serializers.IntegerField(read_only=True)

    class Meta:
        from world.magic.models.soul_tether import (  # noqa: PLC0415
            SineatingPendingOffer,
        )

        model = SineatingPendingOffer
        fields = [
            "id",
            "sinner_sheet_id",
            "sinner_persona_name",
            "scene_id",
            "scene_name",
            "resonance_id",
            "units_offered",
            "anima_cost_per_unit",
            "fatigue_cost_per_unit",
            "created_at",
        ]
        read_only_fields = fields

    def get_sinner_persona_name(self, obj: object) -> str:
        """Return the Sinner's IC display name via their primary persona."""
        return obj.sinner_sheet.display_ic()  # type: ignore[union-attr]


class PendingStageAdvanceOfferSerializer(serializers.ModelSerializer):
    """Sineater-facing view of a pending stage-advance bonus offer (Task 1.7).

    Read-only. Scoped to the authenticated user's character sheets as Sineater.
    The ``expires_at`` field lets the UI show a countdown before the offer lapses.
    """

    sinner_persona_name = serializers.SerializerMethodField()
    sinner_sheet_id = serializers.IntegerField(read_only=True)
    scene_id = serializers.IntegerField(read_only=True)
    scene_name = serializers.CharField(source="scene.name", read_only=True)
    resonance_id = serializers.IntegerField(read_only=True)

    class Meta:
        from world.magic.models.soul_tether import (  # noqa: PLC0415
            PendingStageAdvanceOffer,
        )

        model = PendingStageAdvanceOffer
        fields = [
            "id",
            "sinner_sheet_id",
            "sinner_persona_name",
            "scene_id",
            "scene_name",
            "resonance_id",
            "sinner_corruption_stage",
            "commit_units_max",
            "strain_cost_per_unit",
            "created_at",
            "expires_at",
        ]
        read_only_fields = fields

    def get_sinner_persona_name(self, obj: object) -> str:
        """Return the Sinner's IC display name via their primary persona."""
        return obj.sinner_sheet.display_ic()  # type: ignore[union-attr]


class StageAdvanceRespondSerializer(serializers.Serializer):
    """Write serializer for the Sineater's response to a stage-advance prompt (Spec B §8.1).

    The pending offer row is the canonical source of truth for resonance, max units,
    and expiry — the caller only needs to identify the pair and supply their choice.
    ``units_committed=0`` means decline.
    """

    sinner_sheet_id = serializers.IntegerField()
    sineater_sheet_id = serializers.IntegerField()
    units_committed = serializers.IntegerField(min_value=0)

    def validate_sineater_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve + ownership-check: caller must be the Sineater."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate_sinner_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve sinner sheet."""
        try:
            return CharacterSheet.objects.get(pk=value)
        except CharacterSheet.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_CHARACTER_SHEET_NOT_FOUND) from exc

    def create(self, validated_data: dict) -> object:
        """Resolve from the persisted pending offer; surface typed errors as 400.

        Delegates to ``resolve_stage_advance_prompt_from_db`` which looks up the pending
        offer row, validates TTL + co-location, executes resolution, and deletes the row.
        """
        from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
        from world.magic.services.soul_tether import (  # noqa: PLC0415
            resolve_stage_advance_prompt_from_db,
        )

        try:
            return resolve_stage_advance_prompt_from_db(
                sinner_sheet=validated_data["sinner_sheet_id"],
                sineater_sheet=validated_data["sineater_sheet_id"],
                units_committed=validated_data["units_committed"],
            )
        except SoulTetherError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class StageAdvanceBonusResultSerializer(serializers.Serializer):
    """Read serializer for StageAdvanceBonusResult payloads (Task 1.7)."""

    offer_id = serializers.CharField()
    units_committed = serializers.IntegerField()
    hollow_drained = serializers.IntegerField()
    strain_severity_added = serializers.IntegerField()
    declined = serializers.BooleanField()


_ERR_NO_PENDING_AUDERE = "No pending Audere offer found."


class _PendingOfferCharacterMixin:
    """Shared ``get_character_name`` and ``get_advisory_text`` for pending offer serializers.

    Both ``PendingAudereOfferSerializer`` and ``PendingAudereMajoraOfferSerializer``
    expose identical character-name and advisory-text methods.  This mixin
    centralises those two methods to eliminate the duplication.
    """

    def get_character_name(self, obj: object) -> str:
        """IC display name via the primary persona."""
        return obj.character_sheet.display_ic()  # type: ignore[union-attr]

    def get_advisory_text(self, obj: object) -> str:
        """Live corruption advisory; empty string when no stage-3+ corruption."""
        from world.magic.audere import corruption_advisory_for_character  # noqa: PLC0415

        return corruption_advisory_for_character(obj.character_sheet.character)  # type: ignore[union-attr]


class PendingAudereOfferSerializer(_PendingOfferCharacterMixin, serializers.ModelSerializer):
    """Player-facing view of a pending Audere offer (#873). Read-only.

    advisory_text is computed live (never stored) so the corruption
    "character loss" warning is always current.
    """

    character_name = serializers.SerializerMethodField()
    character_sheet_id = serializers.IntegerField(read_only=True)
    advisory_text = serializers.SerializerMethodField()
    intensity_bonus = serializers.SerializerMethodField()
    anima_pool_bonus = serializers.SerializerMethodField()

    class Meta:
        from world.magic.audere import PendingAudereOffer  # noqa: PLC0415

        model = PendingAudereOffer
        fields = [
            "id",
            "character_sheet_id",
            "character_name",
            "fired_intensity",
            "soulfray_stage_order",
            "intensity_bonus",
            "anima_pool_bonus",
            "advisory_text",
            "created_at",
        ]
        read_only_fields = fields

    def _threshold(self) -> "AudereThreshold | None":
        """Memoize the global threshold config once per serializer instance.

        SharedMemoryModel's identity map does not cache ``.first()`` queries,
        so without this each SerializerMethodField would hit the DB per row.
        """
        from world.magic.audere import AudereThreshold  # noqa: PLC0415

        if not hasattr(self, "_threshold_cache"):
            self._threshold_cache = AudereThreshold.objects.first()
        return self._threshold_cache

    def get_intensity_bonus(self, obj: object) -> int:  # noqa: ARG002
        """Intensity bonus the offer would grant (from the global threshold config)."""
        threshold = self._threshold()
        return threshold.intensity_bonus if threshold else 0

    def get_anima_pool_bonus(self, obj: object) -> int:  # noqa: ARG002
        """Anima pool expansion the offer would grant (from the global threshold config)."""
        threshold = self._threshold()
        return threshold.anima_pool_bonus if threshold else 0


class AudereRespondSerializer(serializers.Serializer):
    """Write serializer for the player's Audere decision. accept=false declines."""

    offer_id = serializers.IntegerField()
    accept = serializers.BooleanField()

    def validate_offer_id(self, value: int):
        """Resolve + ownership-check via the offer's character sheet."""
        from world.magic.audere import PendingAudereOffer  # noqa: PLC0415

        try:
            offer = PendingAudereOffer.objects.get(pk=value)
        except PendingAudereOffer.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_NO_PENDING_AUDERE) from exc
        request = self.context.get("request")
        _resolve_account_sheet(offer.character_sheet_id, request)
        return offer

    def create(self, validated_data: dict) -> object:
        """Delegate to resolve_audere_offer; surface typed errors as 400."""
        from world.magic.audere import resolve_audere_offer  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            AudereOfferError,
            AudereOfferStaleError,
        )
        from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

        offer = validated_data["offer_id"]
        try:
            return resolve_audere_offer(offer.pk, accept=validated_data["accept"])
        except CharacterEngagement.DoesNotExist as exc:
            # TOCTOU window: engagement deleted between the staleness re-check
            # and offer_audere's locked read — surface as stale, not a 500.
            raise serializers.ValidationError(AudereOfferStaleError.user_message) from exc
        except AudereOfferError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class AudereOfferResultSerializer(serializers.Serializer):
    """Read serializer for AudereOfferResult (audere.py dataclass)."""

    accepted = serializers.BooleanField()
    intensity_bonus_applied = serializers.IntegerField()
    anima_pool_expanded_by = serializers.IntegerField()
    advisory_text = serializers.CharField(allow_blank=True)


# =============================================================================
# Audere Majora REST surface (#543)
# =============================================================================

_ERR_NO_PENDING_AUDERE_MAJORA = "No pending Crossing offer found."


class EligiblePathSerializer(serializers.Serializer):
    """Read serializer for a single eligible crossing path."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    stage = serializers.IntegerField()
    stage_display = serializers.CharField()
    description = serializers.CharField()


class PendingAudereMajoraOfferSerializer(_PendingOfferCharacterMixin, serializers.ModelSerializer):
    """Player-facing view of a pending Audere Majora (Crossing) offer (#543). Read-only.

    advisory_text is computed live so the corruption warning is always current.
    eligible_paths is computed per-object and memoized to avoid N+1 queries.
    """

    character_name = serializers.SerializerMethodField()
    character_sheet_id = serializers.IntegerField(read_only=True)
    boundary_level = serializers.IntegerField(source="threshold.boundary_level", read_only=True)
    target_stage_display = serializers.SerializerMethodField()
    vision_text = serializers.CharField(source="threshold.vision_text", read_only=True)
    advisory_text = serializers.SerializerMethodField()
    risk_text = serializers.SerializerMethodField()
    eligible_paths = serializers.SerializerMethodField()
    intended_path_id = serializers.SerializerMethodField()

    class Meta:
        from world.magic.audere_majora import PendingAudereMajoraOffer  # noqa: PLC0415

        model = PendingAudereMajoraOffer
        fields = [
            "id",
            "character_sheet_id",
            "character_name",
            "fired_intensity",
            "soulfray_stage_order",
            "boundary_level",
            "target_stage_display",
            "vision_text",
            "advisory_text",
            "risk_text",
            "eligible_paths",
            "intended_path_id",
            "created_at",
        ]
        read_only_fields = fields

    def get_target_stage_display(self, obj: object) -> str:
        """Human-readable label for the target PathStage."""
        return obj.threshold.get_target_stage_display()  # type: ignore[union-attr]

    def get_risk_text(self, obj: object) -> str:  # noqa: ARG002
        """Fixed risk copy (approved verbatim)."""
        return "This is permanent. The crossing cannot be undone — and survival is not promised."

    def _eligible_paths_for_obj(self, obj: object) -> list:
        """Compute eligible paths once per object pk; memoize on serializer instance."""
        from world.magic.audere_majora import eligible_paths_for_threshold  # noqa: PLC0415

        cache_attr = "_eligible_paths_cache"
        if not hasattr(self, cache_attr):
            setattr(self, cache_attr, {})
        cache: dict = getattr(self, cache_attr)
        pk = obj.pk  # type: ignore[union-attr]
        if pk not in cache:
            cache[pk] = eligible_paths_for_threshold(
                obj.character_sheet.character,  # type: ignore[union-attr]
                obj.threshold,  # type: ignore[union-attr]
            )
        return cache[pk]

    def get_eligible_paths(self, obj: object) -> list:
        """Eligible child paths serialized through EligiblePathSerializer."""
        paths = self._eligible_paths_for_obj(obj)
        dicts = [
            {
                "id": p.pk,
                "name": p.name,
                "stage": p.stage,
                "stage_display": p.get_stage_display(),
                "description": p.description,
            }
            for p in paths
        ]
        return EligiblePathSerializer(dicts, many=True).data

    def get_intended_path_id(self, obj: object) -> int | None:
        """Return the PathIntent's intended_path_id if it is among eligible paths, else None."""
        intent = getattr(obj.character_sheet, "path_intent", None)  # noqa: GETATTR_LITERAL
        if intent is None:
            return None
        eligible_pks = {p.pk for p in self._eligible_paths_for_obj(obj)}
        if intent.intended_path_id in eligible_pks:
            return intent.intended_path_id
        return None


class AudereMajoraRespondSerializer(serializers.Serializer):
    """Write serializer for the player's Crossing decision. accept=false declines."""

    offer_id = serializers.IntegerField()
    accept = serializers.BooleanField()
    path_id = serializers.IntegerField(required=False, allow_null=True)
    declaration_text = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=4000,
        trim_whitespace=True,
        default="",
    )

    def validate_offer_id(self, value: int):
        """Resolve + ownership-check via the offer's character sheet."""
        from world.magic.audere_majora import PendingAudereMajoraOffer  # noqa: PLC0415

        try:
            offer = PendingAudereMajoraOffer.objects.get(pk=value)
        except PendingAudereMajoraOffer.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_NO_PENDING_AUDERE_MAJORA) from exc
        request = self.context.get("request")
        _resolve_account_sheet(offer.character_sheet_id, request)
        return offer

    def validate(self, attrs: dict) -> dict:
        """When accepting, path_id is required and declaration_text must be non-blank."""
        accept = attrs.get("accept", False)
        if accept:
            if attrs.get("path_id") is None:
                raise serializers.ValidationError({"path_id": "Choose the path you will become."})
            declaration = attrs.get("declaration_text", "")
            if not declaration.strip():
                raise serializers.ValidationError(
                    {"declaration_text": "Speak — the declaration cannot be empty."}
                )
        return attrs

    def create(self, validated_data: dict) -> object:
        """Delegate to resolve_audere_majora_offer; surface typed errors as 400."""
        from world.magic.audere_majora import resolve_audere_majora_offer  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            AudereMajoraOfferError,
            ProtagonismLockedError,
        )
        from world.magic.types import AlterationGateError  # noqa: PLC0415

        offer = validated_data["offer_id"]
        try:
            return resolve_audere_majora_offer(
                offer.pk,
                accept=validated_data["accept"],
                path_id=validated_data.get("path_id"),
                declaration_text=validated_data.get("declaration_text", ""),
            )
        except ProtagonismLockedError as exc:
            raise serializers.ValidationError(exc.user_message) from exc
        except AlterationGateError as exc:
            raise serializers.ValidationError(exc.user_message) from exc
        except AudereMajoraOfferError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class AudereMajoraCrossingResultSerializer(serializers.Serializer):
    """Read serializer for AudereMajoraCrossingResult dataclass."""

    accepted = serializers.BooleanField()
    level_before = serializers.IntegerField()
    level_after = serializers.IntegerField()
    chosen_path_name = serializers.CharField(allow_blank=True)
    advisory_text = serializers.CharField(allow_blank=True)
    declaration_interaction_id = serializers.IntegerField(allow_null=True)


class CrossXPLockSerializer(serializers.Serializer):
    """Input + dispatch for ThreadViewSet.cross_xp_lock action (Spec A §3.2)."""

    boundary_level = serializers.IntegerField(min_value=1)

    def create(self, validated_data: dict) -> ThreadLevelUnlock:
        from world.magic.exceptions import (  # noqa: PLC0415
            AnchorCapExceeded,
            InvalidImbueAmount,
            XPInsufficient,
        )
        from world.magic.services import cross_thread_xp_lock  # noqa: PLC0415

        thread = self.context["thread"]
        try:
            return cross_thread_xp_lock(
                character_sheet=thread.owner,
                thread=thread,
                boundary_level=validated_data["boundary_level"],
            )
        except (XPInsufficient, AnchorCapExceeded, InvalidImbueAmount) as exc:
            raise serializers.ValidationError(exc.user_message) from exc


# ---------------------------------------------------------------------------
# Thread-pull commit (Spec A §5.4 + §7.4)
# ---------------------------------------------------------------------------

_ERR_COMBAT_CONTEXT_INCOMPLETE = (  # noqa: STRING_LITERAL
    "combat_encounter_id and combat_participant_id must both be set or both absent."
)
_ERR_THREAD_NOT_FOUND_COMMIT = (  # noqa: STRING_LITERAL
    "One or more thread_ids not found or not owned by the character."
)
_ERR_COMBAT_ENCOUNTER_NOT_FOUND = "Combat encounter not found."  # noqa: STRING_LITERAL
_ERR_COMBAT_PARTICIPANT_NOT_FOUND = "Combat participant not found."  # noqa: STRING_LITERAL


class PullActionContextCommitSerializer(serializers.Serializer):
    """Wire shape for the optional ``action_context`` block in a pull commit.

    Extends ``PullActionContextSerializer`` (used by the preview endpoint) with
    the additional fields the commit path consumes: ``combat_participant_id`` and
    the anchor-ID lists.  All fields are optional because ephemeral (non-combat)
    pulls omit them entirely.
    """

    action_kind = serializers.CharField(required=False, allow_blank=True)
    anchors_in_play = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )
    combat_encounter_id = serializers.IntegerField(required=False, allow_null=True)
    combat_participant_id = serializers.IntegerField(required=False, allow_null=True)
    involved_trait_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )
    involved_technique_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )
    involved_object_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )


class ThreadPullCommitRequestSerializer(serializers.Serializer):
    """Request serializer for POST /api/magic/thread-pull-commit/.

    ``character_sheet_id`` is required and must identify a CharacterSheet owned
    by the requesting account (staff may pass any sheet).

    ``action_context`` carries optional combat context.  If
    ``combat_encounter_id`` is set, ``combat_participant_id`` must also be
    set (and vice versa).  Omitting the whole dict or leaving both fields
    absent signals an ephemeral (RP) pull with no CombatPull row written.
    """

    character_sheet_id = serializers.IntegerField()
    resonance_id = serializers.IntegerField()
    tier = serializers.IntegerField(min_value=1, max_value=3)
    thread_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        max_length=20,
    )
    action_context = PullActionContextCommitSerializer(required=False)

    def validate_character_sheet_id(self, value: int) -> "CharacterSheet":
        """Resolve and ownership-check the caller-supplied character_sheet_id."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)

    def validate(self, attrs: dict) -> dict:
        """Cross-field: combat_encounter_id and combat_participant_id must be paired."""
        ctx = attrs.get("action_context") or {}
        has_encounter = bool(ctx.get("combat_encounter_id"))
        has_participant = bool(ctx.get("combat_participant_id"))
        if has_encounter != has_participant:
            raise serializers.ValidationError(_ERR_COMBAT_CONTEXT_INCOMPLETE)
        return attrs

    def create(self, validated_data: dict) -> object:
        """Build PullActionContext, fetch threads, dispatch spend_resonance_for_pull.

        Catches all expected service exceptions and re-raises as
        ``serializers.ValidationError`` so the view stays thin.
        """
        from world.magic.exceptions import (  # noqa: PLC0415
            InvalidImbueAmount,
            NoMatchingWornFacetItemsError,
            ProtagonismLockedError,
            ResonanceInsufficient,
        )
        from world.magic.services.resonance import spend_resonance_for_pull  # noqa: PLC0415
        from world.magic.types import PullActionContext  # noqa: PLC0415

        sheet: CharacterSheet = validated_data["character_sheet_id"]
        resonance_id: int = validated_data["resonance_id"]
        tier: int = validated_data["tier"]
        thread_ids: list[int] = validated_data["thread_ids"]
        ctx_dict: dict = validated_data.get("action_context") or {}

        # Resolve Resonance.
        try:
            resonance = Resonance.objects.get(pk=resonance_id)
        except Resonance.DoesNotExist as exc:
            raise serializers.ValidationError(_ERR_RESONANCE_NOT_FOUND) from exc

        # Resolve threads — filter by owner so non-owned threads surface as
        # "not found" rather than leaking data about other characters.
        threads = list(
            Thread.objects.filter(
                pk__in=thread_ids,
                owner=sheet,
                retired_at__isnull=True,
            ).select_related("resonance", "owner", "target_facet")
        )
        if len(threads) != len(thread_ids):
            raise serializers.ValidationError(_ERR_THREAD_NOT_FOUND_COMMIT)

        # Build PullActionContext.
        combat_encounter = None
        participant = None
        if ctx_dict.get("combat_encounter_id"):
            from world.combat.models import CombatEncounter, CombatParticipant  # noqa: PLC0415

            try:
                combat_encounter = CombatEncounter.objects.get(pk=ctx_dict["combat_encounter_id"])
            except CombatEncounter.DoesNotExist as exc:
                raise serializers.ValidationError(_ERR_COMBAT_ENCOUNTER_NOT_FOUND) from exc
            try:
                participant = CombatParticipant.objects.get(
                    pk=ctx_dict["combat_participant_id"],
                    encounter=combat_encounter,
                )
            except CombatParticipant.DoesNotExist as exc:
                raise serializers.ValidationError(_ERR_COMBAT_PARTICIPANT_NOT_FOUND) from exc

        action_context = PullActionContext(
            combat_encounter=combat_encounter,
            participant=participant,
            involved_traits=tuple(ctx_dict.get("involved_trait_ids") or []),
            involved_techniques=tuple(ctx_dict.get("involved_technique_ids") or []),
            involved_objects=tuple(ctx_dict.get("involved_object_ids") or []),
        )

        try:
            return spend_resonance_for_pull(
                character_sheet=sheet,
                resonance=resonance,
                tier=tier,
                threads=threads,
                action_context=action_context,
            )
        except ProtagonismLockedError as exc:
            raise serializers.ValidationError(exc.user_message) from exc
        except ResonanceInsufficient as exc:
            raise serializers.ValidationError(exc.user_message) from exc
        except InvalidImbueAmount as exc:
            raise serializers.ValidationError(exc.user_message) from exc
        except NoMatchingWornFacetItemsError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class ResolvedPullEffectCommitSerializer(serializers.Serializer):
    """Wire shape for a single ResolvedPullEffect in the commit response.

    Mirrors ResolvedPullEffectSerializer (used for preview) but also exposes
    ``granted_capability_id`` (which the commit path includes) and uses
    source-accessor notation for ``source_thread_id``.
    """

    kind = serializers.CharField()
    authored_value = serializers.IntegerField(allow_null=True)
    level_multiplier = serializers.IntegerField()
    scaled_value = serializers.IntegerField(allow_null=True)
    vital_target = serializers.CharField(allow_null=True)
    source_thread_id = serializers.IntegerField(source="source_thread.pk")
    source_thread_level = serializers.IntegerField()
    source_tier = serializers.IntegerField()
    granted_capability_id = serializers.SerializerMethodField()
    narrative_snippet = serializers.CharField()
    inactive = serializers.BooleanField()
    inactive_reason = serializers.CharField(allow_null=True)

    def get_granted_capability_id(self, obj: object) -> int | None:
        """Return the granted_capability PK, or None if absent."""
        from world.magic.types import ResolvedPullEffect  # noqa: PLC0415

        if isinstance(obj, ResolvedPullEffect) and obj.granted_capability is not None:
            return obj.granted_capability.pk
        return None


class ThreadPullCommitResponseSerializer(serializers.Serializer):
    """Response serializer for POST /api/magic/thread-pull-commit/."""

    resonance_spent = serializers.IntegerField()
    anima_spent = serializers.IntegerField()
    resolved_effects = ResolvedPullEffectCommitSerializer(many=True)


# =============================================================================
# Thread Hub Summary (GET /api/magic/thread-hub-summary/)
# =============================================================================


class _NearXPLockProspectSerializer(serializers.Serializer):
    """One entry in the near-xp-lock list returned by ThreadHubSummaryView."""

    thread_id = serializers.IntegerField()
    boundary_level = serializers.IntegerField()
    xp_cost = serializers.IntegerField()
    dev_points_to_boundary = serializers.IntegerField()


class _ResonanceBalanceSerializer(serializers.Serializer):
    """One resonance balance entry returned by ThreadHubSummaryView."""

    resonance_id = serializers.IntegerField()
    balance = serializers.IntegerField()
    lifetime_earned = serializers.IntegerField()
    flavor_text = serializers.CharField(allow_blank=True)


class _WeavableTraitSerializer(serializers.Serializer):
    """One entry in the weavable_traits list."""

    trait_id = serializers.IntegerField()
    name = serializers.CharField()
    trait_type = serializers.CharField()
    display_value = serializers.FloatField()


class _WeavableTechniqueSerializer(serializers.Serializer):
    """One entry in the weavable_techniques list."""

    technique_id = serializers.IntegerField()
    name = serializers.CharField()
    gift_id = serializers.IntegerField()
    gift_name = serializers.CharField()


class ThreadHubSummarySerializer(serializers.Serializer):
    """Response serializer for GET /api/magic/thread-hub-summary/."""

    balances = _ResonanceBalanceSerializer(many=True)
    ready_thread_ids = serializers.ListField(child=serializers.IntegerField())
    near_xp_lock_thread_ids = _NearXPLockProspectSerializer(many=True)
    blocked_thread_ids = serializers.ListField(child=serializers.IntegerField())
    weaving_eligibility = serializers.DictField(child=serializers.BooleanField())
    weavable_traits = _WeavableTraitSerializer(many=True)
    weavable_techniques = _WeavableTechniqueSerializer(many=True)
    room_property_ids = serializers.ListField(child=serializers.IntegerField())
    weavable_relationship_track_ids = serializers.ListField(child=serializers.IntegerField())


# =============================================================================
# Rooms-by-property (GET /api/magic/rooms-by-property/)
# =============================================================================


class RoomsByPropertyQuerySerializer(serializers.Serializer):
    """Validates query params for RoomsByPropertyView.

    Repeated ``?property_id=N`` params are gathered by the view and fed
    into this serializer as a list, keeping validation declarative.
    """

    property_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )


# =============================================================================
# Response serializers for @extend_schema decorators
# =============================================================================


class CrossXPLockResponseSerializer(serializers.Serializer):
    """Response shape for ThreadViewSet.cross_xp_lock (Spec A §3.2).

    Returned by POST /api/magic/threads/{id}/cross-xp-lock/ on success.
    """

    thread_id = serializers.IntegerField()
    unlocked_level = serializers.IntegerField()
    xp_spent = serializers.IntegerField()


class AcceptTeachingOfferResponseSerializer(serializers.Serializer):
    """Response shape for ThreadWeavingTeachingOfferViewSet.accept (Spec A §6.1).

    Returned by POST /api/magic/teaching-offers/{id}/accept/ on success.
    """

    id = serializers.IntegerField()
    unlock_id = serializers.IntegerField()
    xp_spent = serializers.IntegerField()


class RoomBriefSerializer(serializers.Serializer):
    """One room entry returned by RoomsByPropertyView.

    Response shape: ``{id, name}``.
    """

    id = serializers.IntegerField()
    name = serializers.CharField()


# =============================================================================
# Ritual Session serializers (Covenants Slice B §4.12)
# =============================================================================


class RitualSessionParticipantSummarySerializer(serializers.Serializer):
    """Brief participant row used inside list/detail session serializers."""

    character_sheet_id = serializers.IntegerField(source="character_sheet.pk")
    character_name = serializers.SerializerMethodField()
    state = serializers.CharField()
    responded_at = serializers.DateTimeField(allow_null=True)

    def get_character_name(self, obj: object) -> str:
        """Return primary persona name for the participant's sheet."""
        sheet = getattr(obj, "character_sheet", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            return ""
        persona = getattr(sheet, "primary_persona", None)  # noqa: GETATTR_LITERAL
        return getattr(persona, "name", "") if persona is not None else ""  # noqa: GETATTR_LITERAL


class RitualSessionListSerializer(serializers.ModelSerializer):
    """Read-only serializer for listing RitualSessions (list endpoints).

    Exposes ritual name, initiator name, proposed terms, expiry,
    participant count summary, and the requesting user's role in this session.
    """

    ritual_name = serializers.CharField(source="ritual.name", read_only=True)
    participation_rule = serializers.CharField(source="ritual.participation_rule", read_only=True)
    initiator_name = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = RitualSession
        fields = [
            "id",
            "ritual_name",
            "participation_rule",
            "initiator_name",
            "proposed_terms",
            "expires_at",
            "created_at",
            "participant_count",
            "my_role",
        ]
        read_only_fields = fields

    def get_initiator_name(self, obj: object) -> str:
        """Return primary persona name of the initiator sheet."""
        initiator = getattr(obj, "initiator", None)  # noqa: GETATTR_LITERAL
        if initiator is None:
            return ""
        persona = getattr(initiator, "primary_persona", None)  # noqa: GETATTR_LITERAL
        return getattr(persona, "name", "") if persona is not None else ""  # noqa: GETATTR_LITERAL

    def get_participant_count(self, obj: object) -> dict[str, int]:
        """Return counts by state. Uses participants_cached if prefetched."""
        from world.magic.constants import ParticipantState  # noqa: PLC0415

        # Use participants_cached (populated by Prefetch to_attr) when available.
        cached = getattr(obj, "participants_cached", None)  # noqa: GETATTR_LITERAL
        if cached is not None:
            participants = cached
        else:
            participants = list(getattr(obj, "participants", None).all())  # noqa: GETATTR_LITERAL
        return {
            "invited": sum(1 for p in participants if p.state == ParticipantState.INVITED),
            "accepted": sum(1 for p in participants if p.state == ParticipantState.ACCEPTED),
            "declined": sum(1 for p in participants if p.state == ParticipantState.DECLINED),
            "total": len(participants),
        }

    def get_my_role(self, obj: object) -> dict[str, object]:
        """Return {role: 'initiator'|'participant', state: <ParticipantState|None>}."""
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return {"role": "unknown", "state": None}
        user = request.user
        initiator = getattr(obj, "initiator", None)  # noqa: GETATTR_LITERAL
        # Check if initiator's sheet belongs to this user.
        my_sheet_ids = set(RosterEntry.objects.for_account(user).character_ids())
        if initiator is not None and initiator.pk in my_sheet_ids:
            return {"role": "initiator", "state": None}
        # Check participant rows. Use participants_cached when prefetched.
        cached = getattr(obj, "participants_cached", None)  # noqa: GETATTR_LITERAL
        participants_iter = (
            cached if cached is not None else getattr(obj, "participants", None).all()  # noqa: GETATTR_LITERAL
        )
        for participant in participants_iter:
            if participant.character_sheet_id in my_sheet_ids:
                return {"role": "participant", "state": participant.state}
        return {"role": "unknown", "state": None}


class RitualSessionDetailSerializer(serializers.ModelSerializer):
    """Read-only serializer for the RitualSession detail endpoint.

    Exposes all participants with per-participant state and responded_at,
    plus session_kwargs and a summary of session_references.
    """

    ritual_name = serializers.CharField(source="ritual.name", read_only=True)
    participation_rule = serializers.CharField(source="ritual.participation_rule", read_only=True)
    initiator_id = serializers.IntegerField(source="initiator.pk", read_only=True)
    initiator_name = serializers.SerializerMethodField()
    participants = RitualSessionParticipantSummarySerializer(
        source="participants_cached", many=True, read_only=True
    )
    session_references = serializers.SerializerMethodField()

    class Meta:
        model = RitualSession
        fields = [
            "id",
            "ritual_name",
            "participation_rule",
            "initiator_id",
            "initiator_name",
            "proposed_terms",
            "session_kwargs",
            "expires_at",
            "created_at",
            "participants",
            "session_references",
        ]
        read_only_fields = fields

    def get_initiator_name(self, obj: object) -> str:
        initiator = getattr(obj, "initiator", None)  # noqa: GETATTR_LITERAL
        if initiator is None:
            return ""
        persona = getattr(initiator, "primary_persona", None)  # noqa: GETATTR_LITERAL
        return getattr(persona, "name", "") if persona is not None else ""  # noqa: GETATTR_LITERAL

    def get_session_references(self, obj: object) -> list[dict[str, object]]:
        """Summarise session-level references (participant=None).

        Uses references_cached (populated by Prefetch to_attr) when available,
        filtering in Python. Falls back to a DB .filter() query.
        """
        result = []
        # Prefer prefetched list; fall back to DB query.
        cached = getattr(obj, "references_cached", None)  # noqa: GETATTR_LITERAL
        if cached is not None:
            refs_iter = [r for r in cached if r.participant_id is None]
        else:
            refs = getattr(obj, "references", None)  # noqa: GETATTR_LITERAL
            if refs is None:
                return result
            refs_iter = refs.filter(participant__isnull=True)
        for ref in refs_iter:
            entry: dict[str, object] = {"kind": ref.kind}
            if ref.ref_covenant_id is not None:
                entry["ref_covenant_id"] = ref.ref_covenant_id
            if ref.ref_covenant_role_id is not None:
                entry["ref_covenant_role_id"] = ref.ref_covenant_role_id
            result.append(entry)
        return result


# Error messages for RitualSessionDraftSerializer.
_ERR_RITUAL_NOT_FOUND = "Ritual not found."
_ERR_RITUAL_SINGLE_ACTOR = "Single-actor rituals do not use sessions."
_ERR_INVITEE_NOT_FOUND = "One or more invitee IDs do not match known CharacterSheets."
_ERR_REFERENCE_SPEC_INVALID = (
    "Each reference spec must have 'kind' and exactly one of 'ref_covenant_id' or "
    "'ref_covenant_role_id'."
)
_ERR_EXPIRES_AT_IN_PAST = "expires_at must be in the future."
_ERR_NO_ACTIVE_CHARACTER = "You must have an active character to draft a ritual session."
_ERR_REQUEST_CONTEXT_REQUIRED = "Request context is required."


def _parse_reference_specs(raw_specs: list[dict]) -> list:
    """Convert raw dicts to RitualSessionReferenceSpec instances.

    Validates that each spec has a kind and exactly one ref FK. Raises
    serializers.ValidationError if any spec is malformed.
    """
    from world.covenants.models import Covenant, CovenantRole  # noqa: PLC0415
    from world.magic.constants import ReferenceKind  # noqa: PLC0415
    from world.magic.types.sessions import RitualSessionReferenceSpec  # noqa: PLC0415

    specs = []
    valid_kinds = {ReferenceKind.COVENANT, ReferenceKind.COVENANT_ROLE}
    for raw in raw_specs:
        kind = raw.get("kind")
        covenant_id = raw.get("ref_covenant_id")
        role_id = raw.get("ref_covenant_role_id")
        has_covenant = covenant_id is not None
        has_role = role_id is not None
        if kind not in valid_kinds or not (has_covenant ^ has_role):
            raise serializers.ValidationError(_ERR_REFERENCE_SPEC_INVALID)
        ref_covenant = None
        ref_covenant_role = None
        if has_covenant:
            try:
                ref_covenant = Covenant.objects.get(pk=covenant_id)
            except Covenant.DoesNotExist:
                raise serializers.ValidationError(
                    {"ref_covenant_id": f"Covenant {covenant_id} not found."}
                ) from None
        else:
            try:
                ref_covenant_role = CovenantRole.objects.get(pk=role_id)
            except CovenantRole.DoesNotExist:
                raise serializers.ValidationError(
                    {"ref_covenant_role_id": f"CovenantRole {role_id} not found."}
                ) from None
        specs.append(
            RitualSessionReferenceSpec(
                kind=kind,
                ref_covenant=ref_covenant,
                ref_covenant_role=ref_covenant_role,
            )
        )
    return specs


class RitualSessionDraftSerializer(serializers.Serializer):
    """Write-only serializer for POST /api/rituals/sessions/ (draft a session).

    Validates inputs and resolves PKs to model instances. The view calls
    draft_session(**validated_data) with the resolved data.
    """

    ritual_id = serializers.IntegerField()
    proposed_terms = serializers.CharField(default="", allow_blank=True)
    session_kwargs = serializers.DictField(
        child=serializers.JSONField(binary=False),
        required=False,
        default=dict,
    )
    invitee_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    session_references = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    initiator_participant_kwargs = serializers.DictField(
        child=serializers.JSONField(binary=False),
        required=False,
        default=dict,
    )
    initiator_references = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    expires_at = serializers.DateTimeField(required=False, default=None)

    def validate_ritual_id(self, value: int) -> "Ritual":  # type: ignore[override]
        """Resolve to a Ritual instance; reject SINGLE_ACTOR rituals."""
        from world.magic.constants import ParticipationRule  # noqa: PLC0415

        try:
            ritual = Ritual.objects.get(pk=value)
        except Ritual.DoesNotExist:
            raise serializers.ValidationError(_ERR_RITUAL_NOT_FOUND) from None
        if ritual.participation_rule == ParticipationRule.SINGLE_ACTOR:
            raise serializers.ValidationError(_ERR_RITUAL_SINGLE_ACTOR)
        return ritual

    def validate_invitee_ids(self, value: list[int]) -> "list[CharacterSheet]":  # type: ignore[override]
        """Resolve to CharacterSheet instances."""
        if not value:
            return []
        sheets = list(CharacterSheet.objects.filter(pk__in=value))
        if len(sheets) != len(set(value)):
            raise serializers.ValidationError(_ERR_INVITEE_NOT_FOUND)
        return sheets

    def validate_session_references(self, value: list[dict]) -> list:  # type: ignore[override]
        """Parse and validate reference spec dicts."""
        return _parse_reference_specs(value)

    def validate_initiator_references(self, value: list[dict]) -> list:  # type: ignore[override]
        """Parse and validate initiator reference spec dicts."""
        return _parse_reference_specs(value)

    def validate(self, attrs: dict) -> dict:
        """Resolve initiator from request, set expires_at default, remap keys."""
        import datetime as _dt  # noqa: PLC0415

        from django.utils import timezone  # noqa: PLC0415

        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError(_ERR_REQUEST_CONTEXT_REQUIRED)
        user = request.user
        owned_ids = set(RosterEntry.objects.for_account(user).character_ids())
        if not owned_ids:
            raise serializers.ValidationError(_ERR_NO_ACTIVE_CHARACTER)
        # Pick the first active sheet for the initiator.
        # The spec does not require explicit initiator selection — the user's
        # active character is implicit. If a user has multiple active tenures,
        # the caller should specify via context; for now, take the lowest PK.
        initiator_sheet = CharacterSheet.objects.filter(pk__in=owned_ids).order_by("pk").first()
        if initiator_sheet is None:
            raise serializers.ValidationError(_ERR_NO_ACTIVE_CHARACTER)
        if attrs.get("expires_at") is None:
            attrs["expires_at"] = timezone.now() + _dt.timedelta(hours=24)
        expires_at = attrs["expires_at"]
        if expires_at <= timezone.now():
            raise serializers.ValidationError({"expires_at": _ERR_EXPIRES_AT_IN_PAST})
        # Remap field names to match draft_session keyword arguments.
        attrs["ritual"] = attrs.pop("ritual_id")
        attrs["initiator"] = initiator_sheet
        attrs["invitee_sheets"] = attrs.pop("invitee_ids")
        return attrs


class RitualSessionAcceptSerializer(serializers.Serializer):
    """Write-only serializer for POST /api/rituals/sessions/{id}/accept/.

    Validates the shape of participant_kwargs and references. Deep schema
    validation against participant_fields is future work — services raise
    RequiredReferenceMissingError for missing required choices.
    """

    participant_kwargs = serializers.DictField(
        child=serializers.JSONField(binary=False),
        required=False,
        default=dict,
    )
    references = serializers.ListField(child=serializers.DictField(), required=False, default=list)

    def validate_references(self, value: list[dict]) -> list:  # type: ignore[override]
        """Validate reference spec shape (well-formedness only)."""
        return _parse_reference_specs(value)


# =============================================================================
# Applicable-pulls API (unified combat UI §5)
# =============================================================================


class ApplicablePullsRequestSerializer(serializers.Serializer):
    """Request serializer for POST /api/magic/applicable-pulls/.

    ``character_sheet_id`` is required and must identify a CharacterSheet the
    requesting account owns (staff may pass any sheet). All other fields are
    optional context that narrows which threads are applicable.
    """

    character_sheet_id = serializers.IntegerField()
    technique_id = serializers.IntegerField(required=False, allow_null=True)
    effect_type_id = serializers.IntegerField(required=False, allow_null=True)
    target_object_id = serializers.IntegerField(required=False, allow_null=True)
    target_persona_id = serializers.IntegerField(required=False, allow_null=True)
    scene_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_character_sheet_id(self, value: int) -> CharacterSheet:
        """Resolve + ownership-check the caller-supplied character_sheet_id."""
        request = self.context.get("request")
        return _resolve_account_sheet(value, request)


class ThreadApplicabilitySerializer(serializers.Serializer):
    """One row in the applicable-pulls response.

    Response shape: ``{thread_id, applicable, inapplicable_reason}``.
    ``inapplicable_reason`` is null when ``applicable`` is true.
    """

    thread_id = serializers.IntegerField(source="thread.pk")
    applicable = serializers.BooleanField()
    inapplicable_reason = serializers.CharField(
        source="reason",
        allow_null=True,
        required=False,
    )


# =============================================================================
# Technique Builder serializers (#537) — policy-aware design input
# =============================================================================


class _CapabilityGrantSpecSerializer(serializers.Serializer):
    capability_id = serializers.PrimaryKeyRelatedField(queryset=CapabilityType.objects.all())
    base_value = serializers.IntegerField(default=0)
    intensity_multiplier = serializers.FloatField(default=0.0)


class _DamageProfileSpecSerializer(serializers.Serializer):
    damage_type_id = serializers.PrimaryKeyRelatedField(
        queryset=DamageType.objects.all(), allow_null=True, required=False
    )
    base_damage = serializers.IntegerField(default=0)
    damage_intensity_multiplier = serializers.FloatField(default=0.0)


class _AppliedConditionSpecSerializer(serializers.Serializer):
    condition_id = serializers.PrimaryKeyRelatedField(queryset=ConditionTemplate.objects.all())
    base_severity = serializers.IntegerField(default=1)
    base_duration_rounds = serializers.IntegerField(allow_null=True, required=False)


class TechniqueDesignSerializer(serializers.Serializer):
    """Policy-aware write input for the technique builder.

    Expects ``policy`` (an ``AuthoringPolicy`` instance) and optionally
    ``character`` (a ``CharacterSheet``) in ``context``.  The serializer
    validates FK existence, enforces player gift-ownership, derives
    ``level`` from the tier's ``representative_level``, and stores the
    built ``TechniqueDesignInput`` in ``validated_data["_design"]``.
    """

    name = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, default="")
    gift_id = serializers.IntegerField()
    style_id = serializers.PrimaryKeyRelatedField(queryset=TechniqueStyle.objects.all())
    effect_type_id = serializers.PrimaryKeyRelatedField(queryset=EffectType.objects.all())
    action_category = serializers.CharField(max_length=10)
    tier = serializers.IntegerField(min_value=1, max_value=5)
    intensity = serializers.IntegerField(min_value=0)
    control = serializers.IntegerField(min_value=0)
    anima_cost = serializers.IntegerField(min_value=0)
    restriction_ids = serializers.PrimaryKeyRelatedField(
        queryset=Restriction.objects.all(),
        many=True,
        required=False,
        default=list,
    )
    capability_grants = _CapabilityGrantSpecSerializer(many=True, required=False, default=list)
    damage_profiles = _DamageProfileSpecSerializer(many=True, required=False, default=list)
    applied_conditions = _AppliedConditionSpecSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        from world.magic.services.technique_builder import PlayerPolicy  # noqa: PLC0415

        policy = self.context["policy"]
        character = self.context.get("character")

        gift = Gift.objects.filter(pk=attrs["gift_id"]).first()
        if gift is None:
            raise serializers.ValidationError({"gift_id": "Unknown gift."})

        # Player must own the gift; staff may use any gift.
        if isinstance(policy, PlayerPolicy):
            if (
                character is None
                or not CharacterGift.objects.filter(character=character, gift=gift).exists()
            ):
                raise serializers.ValidationError({"gift_id": "You do not know that gift."})

        attrs["_gift"] = gift
        attrs["_design"] = self._to_design(attrs)
        return attrs

    def _to_design(self, attrs):
        from world.magic.services.technique_builder import (  # noqa: PLC0415
            get_technique_tier_budget,
        )
        from world.magic.types.technique_builder import (  # noqa: PLC0415
            AppliedConditionSpec,
            CapabilityGrantSpec,
            DamageProfileSpec,
            TechniqueDesignInput,
        )

        tier = attrs["tier"]
        level = get_technique_tier_budget(tier).representative_level
        return TechniqueDesignInput(
            name=attrs["name"],
            description=attrs["description"],
            gift_id=attrs["gift_id"],
            style_id=attrs["style_id"].id,
            effect_type_id=attrs["effect_type_id"].id,
            action_category=attrs["action_category"],
            tier=tier,
            intensity=attrs["intensity"],
            control=attrs["control"],
            anima_cost=attrs["anima_cost"],
            level=level,
            restriction_ids=tuple(r.id for r in attrs["restriction_ids"]),
            capability_grants=tuple(
                CapabilityGrantSpec(
                    capability_id=c["capability_id"].id,
                    base_value=c["base_value"],
                    intensity_multiplier=c["intensity_multiplier"],
                )
                for c in attrs["capability_grants"]
            ),
            damage_profiles=tuple(
                DamageProfileSpec(
                    damage_type_id=(
                        d["damage_type_id"].id if d["damage_type_id"] is not None else None
                    ),
                    base_damage=d["base_damage"],
                    damage_intensity_multiplier=d["damage_intensity_multiplier"],
                )
                for d in attrs["damage_profiles"]
            ),
            applied_conditions=tuple(
                AppliedConditionSpec(
                    condition_id=a["condition_id"].id,
                    base_severity=a["base_severity"],
                    base_duration_rounds=a.get("base_duration_rounds"),
                )
                for a in attrs["applied_conditions"]
            ),
        )

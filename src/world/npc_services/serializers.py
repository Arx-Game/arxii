"""DRF serializers for the unified NPC service framework."""

from rest_framework import serializers

from world.clues.models import Clue
from world.npc_services.models import (
    ClueRevealOfferDetails,
    MissionOfferDetails,
    NPCReactionLine,
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
    OfferSummons,
    PermitOfferDetails,
    RecordedProfile,
    StaffingProfile,
    StaffingProfileLine,
)


class NPCStandingSerializer(serializers.ModelSerializer):
    """Staff CRUD for per-(PC persona, NPC persona) affection rows.

    Standing carries affection + interaction summary only — cooldown
    lives on OfferCooldown so it works for every offer kind.
    """

    class Meta:
        model = NPCStanding
        fields = [
            "id",
            "persona",
            "npc_persona",
            "affection",
            "last_interaction_summary",
            "last_changed_at",
        ]
        read_only_fields = ["id", "last_changed_at"]


class NPCRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NPCRole
        fields = [
            "id",
            "name",
            "description",
            "default_description_template",
            "default_rapport_starting_value",
            "faction_affiliation",
            "is_active",
        ]
        read_only_fields = ["id"]


class NPCServiceOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = NPCServiceOffer
        fields = [
            "id",
            "role",
            "kind",
            "label",
            "draw_mode",
            "eligibility_rule",
            "rapport_requirement",
            "is_final",
            "rapport_delta_success",
            "rapport_delta_failure",
            "cooldown",
            "check_type",
            "check_difficulty",
        ]
        read_only_fields = ["id"]


class OfferCooldownSerializer(serializers.ModelSerializer):
    """Staff CRUD for per-(offer, persona) cooldown rows.

    Written by `resolve_offer` on final-action grants; staff can clear
    or extend by editing `available_at` directly.
    """

    class Meta:
        model = OfferCooldown
        fields = ["id", "offer", "persona", "available_at"]
        read_only_fields = ["id"]


class PermitOfferDetailsSerializer(serializers.ModelSerializer):
    """Staff CRUD for permit-kind offer details (#1684, closing #728's residual).

    ``building_kind`` and ``default_approved_wards`` are PK-related writes; the
    FE feeds them from the existing ``/api/buildings/building-kinds/`` and
    areas list endpoints.
    """

    class Meta:
        model = PermitOfferDetails
        fields = [
            "id",
            "offer",
            "building_kind",
            "default_approved_wards",
            "default_max_target_size",
            "permit_cost_currency",
        ]
        read_only_fields = ["id"]


class ClueRevealOfferDetailsSerializer(serializers.ModelSerializer):
    """Staff CRUD for clue-reveal-kind offer details (#3428).

    ``clue`` is written/read by **slug**, not PK — there is no staff-facing
    "browse all clues" listing endpoint to build a picker from (unlike
    ``building_kind``'s existing `/api/buildings/building-kinds/`), and every
    other staff clue-placement surface (`PlaceClueDialog`'s `staff_place_clue`/
    `staff_place_clue_trigger` actions) already takes a clue by slug — this
    stays consistent rather than inventing a clue-id lookup round-trip. Clue
    rows themselves are minted via #3432's `author_clue`, not created here.
    """

    clue = serializers.SlugRelatedField(slug_field="slug", queryset=Clue.objects.all())

    class Meta:
        model = ClueRevealOfferDetails
        fields = ["id", "offer", "clue"]
        read_only_fields = ["id"]


class MissionOfferDetailsSerializer(serializers.ModelSerializer):
    """Staff CRUD for mission-kind offer details (#728).

    ``role`` is denormalized from ``offer.role`` by the model's ``save()``
    override (per #686 Phase 6) so callers never set it directly — it's
    read-only here, and the unique-constraint promise on
    ``(role, mission_template)`` is enforced at the DB level.
    """

    class Meta:
        model = MissionOfferDetails
        fields = [
            "id",
            "offer",
            "role",
            "mission_template",
            "source_beat",
            "target_project",
            "weight",
            "requirements_override",
            "role_cooldown_duration",
            "draw_priority",
        ]
        read_only_fields = ["id", "role"]


# ---------------------------------------------------------------------------
# Interaction state-machine wire shapes (player-facing API).
# Used by `InteractionViewSet` — ephemeral session state lives in
# `request.session`, the serializers describe request/response payloads.
# ---------------------------------------------------------------------------


class InteractionStartRequestSerializer(serializers.Serializer):
    """POST /api/npc-services/interactions/start/ body."""

    role_id = serializers.IntegerField(min_value=1)
    npc_persona_id = serializers.IntegerField(
        min_value=1,
        required=False,
        allow_null=True,
        help_text=(
            "Optional — pass for class-2+ named NPCs whose standing should "
            "be loaded and persisted. Omit / null for class-1 nameless "
            "functionaries."
        ),
    )


class InteractionOfferSerializer(serializers.Serializer):
    """One eligible offer in the interaction state response."""

    id = serializers.IntegerField()
    label = serializers.CharField()
    kind = serializers.CharField()
    is_final = serializers.BooleanField()
    rapport_requirement = serializers.IntegerField()
    # #1770 PR4: the wrapped MissionTemplate's risk_tier for MISSION-kind
    # offers (null otherwise) — surfaced pre-accept so the ack gate
    # (MISSION_RISK_ACK_TIER) is never a surprise.
    risk_tier = serializers.IntegerField(allow_null=True, default=None)


class InteractionStateSerializer(serializers.Serializer):
    """Response shape for start/resolve — current session state."""

    role_id = serializers.IntegerField()
    current_rapport = serializers.IntegerField()
    closed = serializers.BooleanField()
    available_offers = InteractionOfferSerializer(many=True)
    last_result_message = serializers.CharField(required=False, allow_blank=True)


class InteractionResolveRequestSerializer(serializers.Serializer):
    """POST /api/npc-services/interactions/resolve/ body."""

    offer_id = serializers.IntegerField(min_value=1)
    # #1770 PR4: phase two of the risky-mission opt-in — re-send with True
    # after the gate's informed-consent prompt to accept the danger.
    acknowledge_risk = serializers.BooleanField(default=False)


# ---------------------------------------------------------------------------
# Summons — directed-offer wire shapes (#2050).
# ---------------------------------------------------------------------------


class OfferSummonsSerializer(serializers.ModelSerializer):
    """Serializer for a directed-offer summons (#2050)."""

    role_name = serializers.CharField(source="offer.role.name", read_only=True)
    offer_label = serializers.CharField(source="offer.label", read_only=True)

    class Meta:
        model = OfferSummons
        fields = [
            "id",
            "offer",
            "offer_label",
            "role_name",
            "target_persona",
            "message",
            "status",
            "expires_at",
            "created_by",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = ["id", "status", "created_at", "resolved_at", "role_name", "offer_label"]


class OfferSummonsCreateSerializer(serializers.Serializer):
    """POST body for creating a summons (GM/staff only).

    Validates that the offer and target persona exist and that the offer is
    MISSION-kind. Object-level validation lives here so the view stays thin
    and the serializer is the single authority on input correctness.
    """

    offer_id = serializers.IntegerField(min_value=1)
    target_persona_id = serializers.IntegerField(min_value=1)
    message = serializers.CharField(required=False, allow_blank=True, default="")
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        """Resolve the two ids to rows and hand them back in ``validated_data``.

        The resolved instances travel in the returned dict, DRF's own channel for
        them, rather than being stashed on the serializer for the view to read back
        off ``self`` (ADR-0260). Errors stay keyed to the field that carries the id,
        so the response shape is unchanged.
        """
        from world.npc_services.constants import OfferKind  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415

        offer = NPCServiceOffer.objects.filter(pk=attrs["offer_id"]).first()
        if offer is None:
            msg = "That NPC service offer was not found."
            raise serializers.ValidationError({"offer_id": msg})
        if offer.kind != OfferKind.MISSION:
            msg = "Summonses are limited to MISSION-kind offers in v1 (#2050)."
            raise serializers.ValidationError({"offer_id": msg})

        persona = Persona.objects.filter(pk=attrs["target_persona_id"]).first()
        if persona is None:
            msg = "That target persona was not found."
            raise serializers.ValidationError({"target_persona_id": msg})

        return attrs | {"offer": offer, "target_persona": persona}


class SummonsRespondSerializer(serializers.Serializer):
    """POST body for responding to a summons."""

    accept = serializers.BooleanField()
    acknowledge_risk = serializers.BooleanField(required=False, default=False)


class RecordedProfileSerializer(serializers.ModelSerializer):
    """A character's Archive profile sittings + recorded history (#2632)."""

    persona_name = serializers.CharField(source="persona.name", read_only=True)
    era_season_number = serializers.IntegerField(
        source="era.season_number", read_only=True, allow_null=True
    )

    class Meta:
        model = RecordedProfile
        fields = [
            "id",
            "persona",
            "persona_name",
            "status",
            "text",
            "recorded_by_label",
            "price_paid",
            "created_at",
            "recorded_at",
            "ic_date",
            "era_season_number",
        ]
        read_only_fields = fields


class RecordedProfileCompleteSerializer(serializers.Serializer):
    """The write-up text for a COMMISSIONED sitting (#2632)."""

    text = serializers.CharField()


class NPCReactionLineSerializer(serializers.ModelSerializer):
    """Staff CRUD for banded NPC reaction lines (#2632)."""

    class Meta:
        model = NPCReactionLine
        fields = ["id", "role", "functionary", "metric", "band_floor", "template"]


class StaffingProfileLineSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = StaffingProfileLine
        fields = ["id", "profile", "role", "role_name"]


class StaffingProfileSerializer(serializers.ModelSerializer):
    """Staff authoring: a building kind's baseline crew (#2827 phase 1)."""

    lines = StaffingProfileLineSerializer(many=True, read_only=True)
    building_kind_name = serializers.CharField(source="building_kind.name", read_only=True)

    class Meta:
        model = StaffingProfile
        fields = ["id", "building_kind", "building_kind_name", "lines"]

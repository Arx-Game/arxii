"""DRF serializers for the unified NPC service framework."""

from rest_framework import serializers

from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
    PermitOfferDetails,
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
    class Meta:
        model = PermitOfferDetails
        fields = ["id", "offer"]
        read_only_fields = ["id"]


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

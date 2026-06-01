"""DRF serializers for the unified NPC service framework."""

from rest_framework import serializers

from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    PermitOfferDetails,
)


class NPCStandingSerializer(serializers.ModelSerializer):
    """Staff CRUD for per-(PC persona, NPC persona) standing rows.

    Normally written by mission ``accept_mission`` (cooldown side) and
    future flirt/seduce/cultivation checks (affection side). CRUD here
    is for staff overrides — clear a cooldown, bump or penalize
    affection, set an interaction summary.
    """

    class Meta:
        model = NPCStanding
        fields = [
            "id",
            "persona",
            "npc_persona",
            "affection",
            "available_at",
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
        ]
        read_only_fields = ["id"]


class PermitOfferDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermitOfferDetails
        fields = ["id", "offer"]
        read_only_fields = ["id"]

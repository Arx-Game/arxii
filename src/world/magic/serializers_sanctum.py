"""Serializers for the Sanctum API surface (Plan 4 §F)."""

from __future__ import annotations

from rest_framework import serializers

from world.magic.models import SanctumDetails, Thread
from world.magic.services.sanctum_lvm import sum_homecoming_value


class SanctumDetailsSerializer(serializers.ModelSerializer):
    """Read-shape for SanctumDetails surfaced on the player's "My Sanctums" view."""

    level = serializers.IntegerField(source="feature_instance.level", read_only=True)
    room_profile_id = serializers.IntegerField(
        source="feature_instance.room_profile_id", read_only=True
    )
    homecoming_sum = serializers.SerializerMethodField()
    resonance_type_name = serializers.CharField(source="resonance_type.name", read_only=True)

    class Meta:
        model = SanctumDetails
        fields = [
            "feature_instance_id",
            "room_profile_id",
            "level",
            "resonance_type_id",
            "resonance_type_name",
            "owner_mode",
            "last_homecoming_ritual_at",
            "last_purging_ritual_at",
            "pending_sacrifice_overflow",
            "homecoming_sum",
        ]
        read_only_fields = fields

    def get_homecoming_sum(self, obj: SanctumDetails) -> int:
        return sum_homecoming_value(obj)


class SanctumThreadSerializer(serializers.ModelSerializer):
    """Read-shape for a SANCTUM-target Thread."""

    class Meta:
        model = Thread
        fields = [
            "id",
            "owner",
            "target_sanctum_details",
            "slot_kind",
            "level",
            "developed_points",
            "created_at",
            "retired_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Action serializers — request validation for POST endpoints
# ---------------------------------------------------------------------------


class HomecomingActionSerializer(serializers.Serializer):
    resonance_sacrificed = serializers.IntegerField(min_value=1)
    narrative_text = serializers.CharField(allow_blank=True, max_length=4000, default="")


class PurgingActionSerializer(serializers.Serializer):
    new_resonance_id = serializers.IntegerField()
    resonance_sacrificed = serializers.IntegerField(min_value=0)


class WeaveActionSerializer(serializers.Serializer):
    slot_kind = serializers.ChoiceField(choices=["PERSONAL_OWN", "COVENANT", "HELPER"])

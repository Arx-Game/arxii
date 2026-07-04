"""Serializers for the Sanctum API surface (Plan 4 §F)."""

from __future__ import annotations

from rest_framework import serializers

from world.magic.models import SanctumDetails, SanctumPendingPayout, Thread
from world.magic.services.sanctum_lvm import sum_homecoming_value


class SanctumDetailsSerializer(serializers.ModelSerializer):
    """Read-shape for SanctumDetails surfaced on the player's "My Sanctums" view.

    Pending payout fields are per-(sanctum, viewing-user) — they read
    from a ``SanctumPendingPayout`` row keyed on the request user's
    primary persona's CharacterSheet.
    """

    level = serializers.IntegerField(source="feature_instance.level", read_only=True)
    room_profile_id = serializers.IntegerField(
        source="feature_instance.room_profile_id", read_only=True
    )
    homecoming_sum = serializers.SerializerMethodField()
    resonance_type_name = serializers.CharField(source="resonance_type.name", read_only=True)
    pending_weaving = serializers.SerializerMethodField()
    pending_owner_bonus = serializers.SerializerMethodField()
    is_founder = serializers.SerializerMethodField()

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
            "pending_weaving",
            "pending_owner_bonus",
            "is_founder",
        ]
        read_only_fields = fields

    def get_homecoming_sum(self, obj: SanctumDetails) -> int:
        return sum_homecoming_value(obj)

    def _viewer_character_sheet(self):
        viewer_sheet = self.context.get("viewer_character_sheet")
        if viewer_sheet is not None:
            return viewer_sheet
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        from world.roster.models import RosterEntry  # noqa: PLC0415

        entry = RosterEntry.objects.for_account(request.user).first()
        if entry is None:
            return None
        return entry.character_sheet

    def _pending_payout(self, obj: SanctumDetails):
        sheet = self._viewer_character_sheet()
        if sheet is None:
            return None
        return SanctumPendingPayout.objects.filter(
            sanctum=obj, weaver_character_sheet=sheet
        ).first()

    def get_pending_weaving(self, obj: SanctumDetails) -> int:
        payout = self._pending_payout(obj)
        return payout.pending_weaving if payout else 0

    def get_pending_owner_bonus(self, obj: SanctumDetails) -> int:
        payout = self._pending_payout(obj)
        return payout.pending_owner_bonus if payout else 0

    def get_is_founder(self, obj: SanctumDetails) -> bool:
        sheet = self._viewer_character_sheet()
        if sheet is None:
            return False
        return obj.founder_character_sheet_id == sheet.pk


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


class SanctifyActionSerializer(serializers.Serializer):
    room_profile_id = serializers.IntegerField()
    resonance_type_id = serializers.IntegerField()
    owner_mode = serializers.ChoiceField(choices=["PERSONAL", "COVENANT"])
    components = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )

    def validate_components(self, value: list[int]) -> list:
        """Resolve component PKs to ItemInstances (existence only).

        Mirrors ``RitualPerformRequestSerializer.validate_components``
        (``world/magic/serializers.py``) — explicit item-ID selection for the
        web surface, as opposed to the telnet surface's auto-gather-from-
        inventory (``commands.sanctum.CmdSanctum._gather_components``).

        Ownership (``ItemInstance.holder_character_sheet`` against the body
        actually acting in this request — #684) is deliberately NOT checked
        here: the serializer has no reliable way to determine "the actor for
        this specific request" (a per-request puppet, not account-wide
        roster state). That check lives in ``SanctumViewSet.install``, right
        alongside the same ``_resolve_actor`` every other check in that view
        already trusts.
        """
        from world.items.models import ItemInstance  # noqa: PLC0415

        if not value:
            return []
        instances = list(ItemInstance.objects.filter(pk__in=value))
        found_pks = {inst.pk for inst in instances}
        missing = set(value) - found_pks
        if missing:
            msg = f"ItemInstance(s) not found: {sorted(missing)}."
            raise serializers.ValidationError(msg)
        return instances


class HomecomingActionSerializer(serializers.Serializer):
    resonance_sacrificed = serializers.IntegerField(min_value=1)
    narrative_text = serializers.CharField(allow_blank=True, max_length=4000, default="")


class PurgingActionSerializer(serializers.Serializer):
    new_resonance_id = serializers.IntegerField()
    resonance_sacrificed = serializers.IntegerField(min_value=0)


class WeaveActionSerializer(serializers.Serializer):
    slot_kind = serializers.ChoiceField(choices=["PERSONAL_OWN", "COVENANT", "HELPER"])

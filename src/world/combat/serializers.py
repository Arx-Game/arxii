"""Serializers for combat API endpoints."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from world.combat.constants import ActionCategory, OpponentTier
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)
from world.fatigue.constants import EffortLevel
from world.roster.models import RosterEntry
from world.scenes.models import Scene

# ---------------------------------------------------------------------------
# Nested read serializers
# ---------------------------------------------------------------------------


class OpponentSerializer(serializers.ModelSerializer):
    """Read serializer for combat opponents."""

    class Meta:
        model = CombatOpponent
        fields = [
            "id",
            "name",
            "description",
            "tier",
            "health",
            "max_health",
            "soak_value",
            "probing_current",
            "probing_threshold",
            "current_phase",
            "status",
        ]


class ParticipantSerializer(serializers.ModelSerializer):
    """Read serializer for combat participants.

    Vitals (health, max_health, character_status) are private by default.
    Only visible to staff, the scene GM, or the player who owns the
    character — same visibility rules as character sheets.
    """

    character_name = serializers.CharField(
        source="character_sheet.character.db_key",
        read_only=True,
    )
    health = serializers.SerializerMethodField()
    max_health = serializers.SerializerMethodField()
    character_status = serializers.SerializerMethodField()

    class Meta:
        model = CombatParticipant
        fields = [
            "id",
            "character_name",
            "status",
            "health",
            "max_health",
            "character_status",
        ]

    def _can_view_vitals(self, obj: CombatParticipant) -> bool:
        """Check if the requesting user can see this participant's vitals.

        Allowed for: staff, scene GMs, or the player who owns the character.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        # Check if viewer owns this character
        viewer_character_ids = self.context.get("viewer_character_ids")
        if viewer_character_ids is None:
            active_entries = RosterEntry.objects.for_account(request.user)
            viewer_character_ids = set(
                active_entries.values_list("character_id", flat=True),
            )
            self.context["viewer_character_ids"] = viewer_character_ids
        if obj.character_sheet.character_id in viewer_character_ids:
            return True
        # Check if viewer is GM of the encounter's scene
        is_gm = self.context.get("is_gm")
        if is_gm is not None:
            return is_gm
        # Fall back to direct check if context not set
        encounter = obj.encounter
        if encounter.scene_id:
            return Scene.objects.filter(
                pk=encounter.scene_id,
                participations__account=request.user,
                participations__is_gm=True,
            ).exists()
        return False

    def get_health(self, obj: CombatParticipant) -> int | None:
        """Return current health — only if viewer has permission."""
        if not self._can_view_vitals(obj):
            return None
        try:
            return obj.character_sheet.vitals.health
        except Exception:  # noqa: BLE001
            return None

    def get_max_health(self, obj: CombatParticipant) -> int | None:
        """Return max health — only if viewer has permission."""
        if not self._can_view_vitals(obj):
            return None
        try:
            return obj.character_sheet.vitals.max_health
        except Exception:  # noqa: BLE001
            return None

    def get_character_status(self, obj: CombatParticipant) -> str | None:
        """Return life status — only if viewer has permission."""
        if not self._can_view_vitals(obj):
            return None
        try:
            return obj.character_sheet.vitals.status
        except Exception:  # noqa: BLE001
            return None


class RoundActionSerializer(serializers.ModelSerializer):
    """Read serializer for declared actions."""

    participant_name = serializers.CharField(
        source="participant.character_sheet.character.db_key",
        read_only=True,
    )

    class Meta:
        model = CombatRoundAction
        fields = [
            "id",
            "participant",
            "participant_name",
            "round_number",
            "focused_category",
            "effort_level",
            "focused_action",
            "focused_target",
            "physical_passive",
            "social_passive",
            "mental_passive",
            "combo_upgrade",
            "is_ready",
        ]


# ---------------------------------------------------------------------------
# List and detail serializers
# ---------------------------------------------------------------------------


class EncounterListSerializer(serializers.ModelSerializer):
    """Lightweight listing serializer for combat encounters."""

    participant_count = serializers.SerializerMethodField()
    opponent_count = serializers.SerializerMethodField()

    class Meta:
        model = CombatEncounter
        fields = [
            "id",
            "scene",
            "encounter_type",
            "status",
            "round_number",
            "pace_mode",
            "pace_timer_minutes",
            "is_paused",
            "participant_count",
            "opponent_count",
        ]

    def get_participant_count(self, obj: CombatEncounter) -> int:
        """Return participant count, preferring cached list."""
        try:
            return len(obj.participants_cached)  # type: ignore[attr-defined]
        except AttributeError:
            return obj.participants.count()

    def get_opponent_count(self, obj: CombatEncounter) -> int:
        """Return opponent count, preferring cached list."""
        try:
            return len(obj.opponents_cached)  # type: ignore[attr-defined]
        except AttributeError:
            return obj.opponents.count()


class EncounterDetailSerializer(serializers.ModelSerializer):
    """Full encounter state with covenant-filtered action visibility."""

    participants = ParticipantSerializer(
        many=True,
        read_only=True,
        source="participants_cached",
    )
    opponents = OpponentSerializer(
        many=True,
        read_only=True,
        source="opponents_cached",
    )
    current_round_actions = serializers.SerializerMethodField()
    is_participant = serializers.SerializerMethodField()
    is_gm = serializers.SerializerMethodField()

    class Meta:
        model = CombatEncounter
        fields = [
            "id",
            "scene",
            "encounter_type",
            "status",
            "round_number",
            "risk_level",
            "stakes_level",
            "pace_mode",
            "pace_timer_minutes",
            "is_paused",
            "round_started_at",
            "created_at",
            "participants",
            "opponents",
            "current_round_actions",
            "is_participant",
            "is_gm",
        ]

    def to_representation(self, instance: CombatEncounter) -> dict[str, Any]:
        """Inject is_gm into context before nested serializers run."""
        self.context["is_gm"] = self._is_gm_cached(instance)
        return super().to_representation(instance)

    def get_is_participant(self, obj: CombatEncounter) -> bool:
        """Check whether the requesting user has a character in this encounter."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        active_entries = RosterEntry.objects.for_account(request.user)
        character_ids = set(
            active_entries.values_list("character_id", flat=True),
        )
        return any(
            p.character_sheet.character_id in character_ids
            for p in obj.participants_cached  # type: ignore[attr-defined]
        )

    def get_is_gm(self, obj: CombatEncounter) -> bool:
        """Check whether the requesting user is GM of the linked scene."""
        return self._is_gm_cached(obj)

    def _is_gm_cached(self, obj: CombatEncounter) -> bool:
        """Return cached GM check for the requesting user."""
        cache_key = f"_is_gm_{obj.pk}"
        if not hasattr(self, cache_key):
            request = self.context.get("request")
            if not request or not request.user.is_authenticated or not obj.scene_id:
                setattr(self, cache_key, False)
            else:
                setattr(
                    self,
                    cache_key,
                    Scene.objects.filter(
                        pk=obj.scene_id,
                        participations__account=request.user,
                        participations__is_gm=True,
                    ).exists(),
                )
        return getattr(self, cache_key)

    def get_current_round_actions(
        self,
        obj: CombatEncounter,
    ) -> list[dict[str, Any]]:
        """Return actions visible to the requesting user.

        Covenant-scoped: participants see own covenant's actions.
        GMs and staff see all.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return []

        actions = CombatRoundAction.objects.filter(
            participant__encounter=obj,
            round_number=obj.round_number,
        ).select_related(
            "participant__character_sheet__character",
        )

        # Staff and GMs see all actions
        if request.user.is_staff or self._is_gm_cached(obj):
            return RoundActionSerializer(actions, many=True).data  # type: ignore[return-value]

        # Participants see their covenant's actions.
        # For now (covenants not fully built), show own actions only.
        active_entries = RosterEntry.objects.for_account(request.user)
        character_ids = set(
            active_entries.values_list("character_id", flat=True),
        )
        own_actions = actions.filter(
            participant__character_sheet__character_id__in=character_ids,
        )
        return RoundActionSerializer(own_actions, many=True).data  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Write serializers
# ---------------------------------------------------------------------------


class DeclareActionSerializer(serializers.Serializer):
    """Write serializer for action declaration."""

    focused_action = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    focused_category = serializers.ChoiceField(
        choices=ActionCategory.choices,
        required=False,
        allow_null=True,
    )
    effort_level = serializers.ChoiceField(
        choices=EffortLevel.choices,
        default=EffortLevel.MEDIUM,
    )
    focused_target = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    physical_passive = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    social_passive = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    mental_passive = serializers.IntegerField(
        required=False,
        allow_null=True,
    )


class RemoveParticipantSerializer(serializers.Serializer):
    """Write serializer for removing a participant from an encounter."""

    participant_id = serializers.IntegerField()


class UpgradeComboSerializer(serializers.Serializer):
    """Write serializer for upgrading an action to a combo."""

    combo_id = serializers.IntegerField()


class AddParticipantSerializer(serializers.Serializer):
    """Write serializer for adding a participant to an encounter."""

    character_sheet_id = serializers.IntegerField()
    covenant_role_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )


class AddOpponentSerializer(serializers.Serializer):
    """Write serializer for adding an opponent to an encounter."""

    name = serializers.CharField(max_length=200)
    tier = serializers.ChoiceField(choices=OpponentTier.choices)
    max_health = serializers.IntegerField(min_value=1)
    threat_pool_id = serializers.IntegerField()
    description = serializers.CharField(required=False, default="")
    soak_value = serializers.IntegerField(required=False, default=0)
    probing_threshold = serializers.IntegerField(
        required=False,
        allow_null=True,
    )

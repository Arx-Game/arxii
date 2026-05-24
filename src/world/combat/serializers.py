"""Serializers for combat API endpoints."""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import serializers

from actions.errors import ActionDispatchError
from world.combat.constants import ActionCategory, ClashActionSlot, ClashStatus, OpponentTier
from world.combat.models import (
    Clash,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)
from world.fatigue.constants import EffortLevel
from world.magic.models import CharacterTechnique, Technique

# ---------------------------------------------------------------------------
# Nested read serializers
# ---------------------------------------------------------------------------


class OpponentSerializer(serializers.ModelSerializer):
    """Read serializer for combat opponents.

    Soak value and probing threshold are GM-only — players discover
    these through gameplay (probing attacks, combo availability).
    """

    soak_value = serializers.SerializerMethodField()
    probing_threshold = serializers.SerializerMethodField()

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

    def _is_gm_or_staff(self) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        return self.context.get("is_gm", False)

    def get_soak_value(self, obj: CombatOpponent) -> int | None:
        """Soak value — GM/staff only."""
        return obj.soak_value if self._is_gm_or_staff() else None

    def get_probing_threshold(self, obj: CombatOpponent) -> int | None:
        """Probing threshold — GM/staff only."""
        return obj.probing_threshold if self._is_gm_or_staff() else None


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
        # Check if viewer owns this character. Reads the context entry
        # populated by EncounterDetailSerializer._build_serializer_context,
        # falling back to the Account-level cached property.
        viewer_character_ids = self.context.get("viewer_character_ids")
        if viewer_character_ids is None:
            try:
                viewer_character_ids = request.user.played_character_sheet_ids
            except AttributeError:
                viewer_character_ids = frozenset()
            self.context["viewer_character_ids"] = viewer_character_ids
        if obj.character_sheet.character_id in viewer_character_ids:
            return True
        # Check GM status — prefer cached value, fall back to model method
        is_gm = self.context.get("is_gm")
        if is_gm is None:
            encounter = obj.encounter
            is_gm = encounter.scene.is_gm(request.user) if encounter.scene else False
        return is_gm

    def get_health(self, obj: CombatParticipant) -> int | None:
        """Return current health — only if viewer has permission."""
        if not self._can_view_vitals(obj):
            return None
        try:
            return obj.character_sheet.vitals.health
        except AttributeError:
            return None

    def get_max_health(self, obj: CombatParticipant) -> int | None:
        """Return max health — only if viewer has permission."""
        if not self._can_view_vitals(obj):
            return None
        try:
            return obj.character_sheet.vitals.max_health
        except AttributeError:
            return None

    def get_character_status(self, obj: CombatParticipant) -> str | None:
        """Return life status — only if viewer has permission."""
        if not self._can_view_vitals(obj):
            return None
        try:
            return obj.character_sheet.vitals.status
        except AttributeError:
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
            "focused_opponent_target",
            "focused_ally_target",
            "physical_passive",
            "social_passive",
            "mental_passive",
            "combo_upgrade",
            "is_ready",
        ]


# ---------------------------------------------------------------------------
# Clash state serializer (for EncounterDetailSerializer.clashes)
# ---------------------------------------------------------------------------


class ClashStateSerializer(serializers.ModelSerializer):
    """Compact read serializer for an active Clash, surfaced on EncounterDetail.

    Exposes the fields needed by the frontend ActiveState rail section:
    - id, flavor, status, progress, pc_win_threshold, npc_win_threshold
    - npc_opponent_id (for labelling the clash target)

    Phase 8, Task 8.4 — unified-combat-ui plan.
    """

    class Meta:
        model = Clash
        fields = [
            "id",
            "flavor",
            "status",
            "progress",
            "pc_win_threshold",
            "npc_win_threshold",
            "npc_opponent",
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
    clashes = serializers.SerializerMethodField()

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
            "clashes",
        ]

    def to_representation(self, instance: CombatEncounter) -> dict[str, Any]:
        """Inject is_gm into context before nested serializers run.

        NOTE: This serializer must NOT be used with many=True — the is_gm
        value would leak across encounters. Use EncounterListSerializer
        for list views.
        """
        self.context["is_gm"] = self._compute_is_gm(instance)
        return super().to_representation(instance)

    def get_is_participant(self, obj: CombatEncounter) -> bool:
        """Check whether the requesting user has a character in this encounter."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        character_ids = self._get_viewer_character_ids(request)
        return any(
            p.character_sheet.character_id in character_ids
            for p in obj.participants_cached  # type: ignore[attr-defined]
        )

    def _get_viewer_character_ids(self, request: object) -> set[int] | frozenset[int]:
        """Get character_sheet IDs for the requesting user.

        Resolution order:
        1. Serializer context (populated by ``_build_serializer_context``)
        2. ``request.user.played_character_sheet_ids`` (cached on the
           Account typeclass; invalidated by RosterTenure mutations)
        Caches into context after fetching so subsequent fields in the
        same serializer pass don't re-read.
        """
        cached = self.context.get("viewer_character_ids")
        if cached is not None:
            return cached
        try:
            character_ids = request.user.played_character_sheet_ids  # type: ignore[union-attr]
        except AttributeError:
            character_ids = frozenset()
        self.context["viewer_character_ids"] = character_ids
        return character_ids

    def get_is_gm(self, obj: CombatEncounter) -> bool:
        """Check whether the requesting user is GM of the linked scene."""
        cached = self.context.get("is_gm")
        if cached is not None:
            return cached
        return self._compute_is_gm(obj)

    def _compute_is_gm(self, obj: CombatEncounter) -> bool:
        """Compute GM status for the requesting user.

        Uses the select_related scene and Scene.is_gm() which reads
        from participations_cached — no extra queries.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated or not obj.scene:
            return False
        return obj.scene.is_gm(request.user)

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
        if request.user.is_staff or self.context.get("is_gm", False):
            return RoundActionSerializer(actions, many=True).data  # type: ignore[return-value]

        # Participants see their covenant's actions.
        # For now (covenants not fully built), show own actions only.
        character_ids = self.context.get("viewer_character_ids", set())
        own_actions = actions.filter(
            participant__character_sheet__character_id__in=character_ids,
        )
        return RoundActionSerializer(own_actions, many=True).data  # type: ignore[return-value]

    def get_clashes(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return active Clash records for this encounter.

        Phase 8, Task 8.4 — exposes clash state to the frontend ActiveState
        rail section. Returns only ACTIVE clashes so resolved ones don't litter
        the UI after the clash is done.

        Uses the ``clashes_cached`` prefetch-to-attr set on the viewset's
        ``_base_queryset`` so no extra query fires during detail serialization.
        Falls back to a direct filter for callers that don't use the viewset
        (e.g. unit tests that call the serializer directly).
        """
        clashes = getattr(obj, "clashes_cached", None)
        if clashes is None:
            clashes = (
                Clash.objects.filter(
                    encounter=obj,
                    status=ClashStatus.ACTIVE,
                )
                .select_related("npc_opponent")
                .all()
            )
        return ClashStateSerializer(clashes, many=True).data  # type: ignore[return-value]


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
    focused_opponent_target = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    focused_ally_target = serializers.IntegerField(
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

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate that a focused_action technique is combat-ready."""
        focused_action_id = attrs.get("focused_action")
        if focused_action_id is not None:
            technique = get_object_or_404(Technique, pk=focused_action_id)
            if technique.action_template is None:
                raise serializers.ValidationError(
                    {
                        "focused_action": ActionDispatchError(
                            ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY
                        ).user_message,
                    }
                )
        return attrs


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


class JoinEncounterSerializer(serializers.Serializer):
    """Write serializer for a player self-joining an encounter.

    Requires explicit ``character_sheet_id`` — never auto-selects which
    of the user's characters joins. The view validates that the chosen
    sheet belongs to one of the user's active tenures.
    """

    character_sheet_id = serializers.IntegerField(min_value=1)


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


class DeclareClashContributionSerializer(serializers.Serializer):
    """Write serializer for declaring a PC's clash contribution for the current round.

    Expects ``participant`` (a ``CombatParticipant`` instance) in serializer context.
    Validates clash state, ownership, and the passive anima cap.  Resolves FK PKs to
    model instances so the service function receives clean, typed inputs.
    """

    clash = serializers.IntegerField()
    action_slot = serializers.ChoiceField(choices=ClashActionSlot.choices)
    technique = serializers.IntegerField()
    strain_commitment = serializers.IntegerField(min_value=0)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Resolve FKs and enforce clash-state, ownership, and passive-cap rules."""
        from world.combat.services import get_clash_config  # noqa: PLC0415 — avoids circular import

        participant: CombatParticipant = self.context["participant"]

        # --- Resolve Clash ---
        try:
            clash = Clash.objects.get(pk=attrs["clash"])
        except Clash.DoesNotExist as exc:
            raise serializers.ValidationError({"clash": "Clash not found."}) from exc

        # Clash must be ACTIVE.
        if clash.status != ClashStatus.ACTIVE:
            raise serializers.ValidationError(
                {"clash": "Clash is not active and cannot accept contributions."}
            )

        # Clash must belong to the participant's encounter.
        if clash.encounter_id != participant.encounter_id:
            raise serializers.ValidationError(
                {"clash": "Clash does not belong to the participant's encounter."}
            )

        # --- Resolve Technique ---
        try:
            technique = Technique.objects.get(pk=attrs["technique"])
        except Technique.DoesNotExist as exc:
            raise serializers.ValidationError({"technique": "Technique not found."}) from exc

        # Participant must own the technique.
        owns = CharacterTechnique.objects.filter(
            character=participant.character_sheet,
            technique=technique,
        ).exists()
        if not owns:
            raise serializers.ValidationError({"technique": "You do not know this technique."})

        # --- Passive anima cap ---
        action_slot = attrs["action_slot"]
        strain_commitment = attrs["strain_commitment"]
        if action_slot == ClashActionSlot.PASSIVE:
            config = get_clash_config()
            if strain_commitment > config.passive_anima_cap:
                raise serializers.ValidationError(
                    {
                        "strain_commitment": (
                            f"Passive contributions may not commit more than "
                            f"{config.passive_anima_cap} anima (got {strain_commitment})."
                        )
                    }
                )

        return {
            "clash": clash,
            "action_slot": action_slot,
            "technique": technique,
            "strain_commitment": strain_commitment,
        }

"""Outcome details API for the pose-log expand/collapse UX.

GET /api/combat/action-outcome-details/?action_interaction_ids=N,M,...

Returns structured per-action effects (combo, conditions applied, check
outcome, target status) derived from existing models — no audit tables.
The outcome panel renders these rows directly.

Phase 5 — combat-resolution-loop PR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.combat.constants import OpponentStatus
from world.combat.models import ClashContribution, CombatRoundAction

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter

_ERR_NON_INTEGER_IDS = "action_interaction_ids must be comma-separated integers."


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeepLinkRef:
    """A typed reference to a modal detail view."""

    modal: str
    id: int


@dataclass
class EffectRow:
    """A single effect entry in an action's outcome detail."""

    kind: str
    label: str
    deep_link: DeepLinkRef | None


@dataclass
class ActionOutcomeDetail:
    """All effects for one ACTION Interaction."""

    action_interaction_id: int
    effects: list[EffectRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class OutcomeDetailsQuerySerializer(serializers.Serializer):
    """Validates the ``action_interaction_ids`` query parameter."""

    action_interaction_ids = serializers.CharField(default="")

    def validate_action_interaction_ids(self, value: str) -> list[int]:
        if not value:
            return []
        parts = [p.strip() for p in value.split(",") if p.strip()]
        try:
            return [int(p) for p in parts]
        except ValueError as exc:
            raise serializers.ValidationError(_ERR_NON_INTEGER_IDS) from exc


class DeepLinkRefSerializer(serializers.Serializer):
    modal = serializers.CharField()
    id = serializers.IntegerField()


class EffectRowSerializer(serializers.Serializer):
    kind = serializers.CharField()
    label = serializers.CharField()
    deep_link = serializers.SerializerMethodField()

    def get_deep_link(self, obj: EffectRow) -> dict[str, int | str] | None:
        if obj.deep_link is None:
            return None
        return {"modal": obj.deep_link.modal, "id": obj.deep_link.id}


class OutcomeDetailSerializer(serializers.Serializer):
    action_interaction_id = serializers.IntegerField()
    effects = EffectRowSerializer(many=True)


# ---------------------------------------------------------------------------
# Permission helper
# ---------------------------------------------------------------------------


def _viewer_can_see(user: object, encounter: CombatEncounter) -> bool:
    """Return True iff the user can view this encounter's effects.

    Staff and the encounter's scene GM see everything. Encounter participants
    (PCs in the fight) and scene participants (anyone in the scene) also see
    effects. Other users see nothing — the view returns an empty effects list.
    """
    if not getattr(user, "is_authenticated", False):  # noqa: GETATTR_LITERAL — duck-typing user
        return False
    if getattr(user, "is_staff", False):  # noqa: GETATTR_LITERAL — duck-typing user
        return True
    if encounter.scene is not None and encounter.scene.is_gm(user):
        return True
    # Check participation by walking played_character_sheet_ids.
    viewer_character_ids = getattr(user, "played_character_sheet_ids", frozenset())  # noqa: GETATTR_LITERAL
    for participant in encounter.participants.all():
        if participant.character_sheet.character_id in viewer_character_ids:
            return True
    return False


# ---------------------------------------------------------------------------
# Effect derivation
# ---------------------------------------------------------------------------


class _RoundActionEffects:
    """Per-action lazy collector — derives effect rows from existing models."""

    def __init__(self, action: CombatRoundAction) -> None:
        self.action = action

    @cached_property
    def rows(self) -> list[EffectRow]:
        result: list[EffectRow] = []
        self._add_combo_row(result)
        self._add_target_status_row(result)
        self._add_condition_rows(result)
        return result

    def _add_combo_row(self, result: list[EffectRow]) -> None:
        if self.action.combo_upgrade_id:
            combo = self.action.combo_upgrade
            result.append(
                EffectRow(
                    kind="combo",
                    label=f"Combo: {combo.name}",
                    deep_link=DeepLinkRef(modal="combo", id=combo.pk),
                )
            )

    def _add_target_status_row(self, result: list[EffectRow]) -> None:
        target_opponent = self.action.focused_opponent_target
        if target_opponent is not None and target_opponent.status == OpponentStatus.DEFEATED:
            result.append(
                EffectRow(
                    kind="status",
                    label=f"{target_opponent.name} defeated",
                    deep_link=DeepLinkRef(modal="opponent", id=target_opponent.pk),
                )
            )
        target_ally = self.action.focused_ally_target
        if target_ally is not None:
            from world.vitals.services import can_act, is_dead  # noqa: PLC0415

            ally_character = target_ally.character_sheet.character
            status_word: str | None = None
            if is_dead(ally_character):
                status_word = "dead"
            elif not can_act(ally_character):
                # Not dead but cannot act → incapacitated (Unconscious condition).
                status_word = "incapacitated"
            if status_word is not None:
                result.append(
                    EffectRow(
                        kind="status",
                        label=f"{ally_character.db_key} {status_word}",
                        deep_link=DeepLinkRef(modal="participant", id=target_ally.pk),
                    )
                )

    def _add_condition_rows(self, result: list[EffectRow]) -> None:
        """Conditions applied around this action's resolution.

        Correlated via source_technique + applied_at window matching the
        round-resolve span. Adequate for v1; over-attribution on the
        same-technique-twice edge case is documented as a known limit.
        """
        if self.action.focused_action_id is None:
            return
        # Window: from the round's start to "now"-ish. We use the action's
        # interaction_timestamp (set at resolve-time) as the upper bound, and
        # the encounter's round_started_at as the lower bound. If neither is
        # set, no conditions are reported.
        upper = self.action.interaction_timestamp
        lower = self.action.participant.encounter.round_started_at
        if upper is None or lower is None:
            return

        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        source_character = self.action.participant.character_sheet.character
        condition_instances = ConditionInstance.objects.filter(
            source_character=source_character,
            source_technique_id=self.action.focused_action_id,
            applied_at__gte=lower,
            applied_at__lte=upper,
        ).select_related("condition", "target")

        for ci in condition_instances:
            target_name = ci.target.db_key if ci.target_id else "target"
            result.append(
                EffectRow(
                    kind="condition",
                    label=f"Applied {ci.condition.name} to {target_name}",
                    deep_link=DeepLinkRef(modal="condition", id=ci.pk),
                )
            )


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


def _build_outcome_detail(
    action_interaction_id: int,
    user: object,
) -> ActionOutcomeDetail:
    """Derive effect rows from existing models for one ACTION Interaction.

    Walks Interaction.pk → CombatRoundAction (or ClashContribution) → effects
    derived from action.combo_upgrade, ConditionInstance correlation, and
    target status. No audit-row reads — purely derived from existing state.
    """
    # Try CombatRoundAction first.
    action = (
        CombatRoundAction.objects.filter(interaction_id=action_interaction_id)
        .select_related(
            "participant__encounter__scene",
            "participant__character_sheet",
            "focused_action",
            "focused_opponent_target",
            "focused_ally_target",
            "focused_ally_target__character_sheet",
            "combo_upgrade",
        )
        .first()
    )
    if action is not None:
        if not _viewer_can_see(user, action.participant.encounter):
            return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=[])
        effects = _RoundActionEffects(action).rows
        return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=effects)

    # Fall back to ClashContribution.
    contribution = (
        ClashContribution.objects.filter(interaction_id=action_interaction_id)
        .select_related(
            "clash_round__clash__encounter__scene",
            "clash_round__clash__npc_opponent",
            "technique",
            "check_outcome",
            "character",
        )
        .first()
    )
    if contribution is not None:
        encounter = contribution.clash_round.clash.encounter
        if not _viewer_can_see(user, encounter):
            return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=[])
        return _build_clash_contribution_detail(contribution, action_interaction_id)

    return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=[])


def _build_clash_contribution_detail(
    contribution: ClashContribution,
    action_interaction_id: int,
) -> ActionOutcomeDetail:
    """Render rows directly from ClashContribution fields."""
    effects: list[EffectRow] = []
    clash = contribution.clash_round.clash
    opponent_name = clash.npc_opponent.name if clash.npc_opponent_id else "?"

    effects.append(
        EffectRow(
            kind="clash_progress",
            label=(
                f"Progress {'+' if contribution.progress_delta >= 0 else ''}"
                f"{contribution.progress_delta} on {clash.get_flavor_display()} "
                f"vs {opponent_name}"
            ),
            deep_link=DeepLinkRef(modal="clash", id=clash.pk),
        )
    )
    if contribution.anima_committed > 0:
        effects.append(
            EffectRow(
                kind="anima",
                label=f"Anima committed: {contribution.anima_committed}",
                deep_link=None,
            )
        )
    if contribution.was_audere:
        effects.append(
            EffectRow(
                kind="audere",
                label="Audere fired",
                deep_link=None,
            )
        )
    if contribution.soulfray_severity_accrued > 0:
        effects.append(
            EffectRow(
                kind="soulfray",
                label=f"Soulfray severity +{contribution.soulfray_severity_accrued}",
                deep_link=None,
            )
        )
    return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=effects)


class ActionOutcomeDetailsView(APIView):
    """Return outcome details for a list of ACTION Interaction IDs.

    Query parameter: ``action_interaction_ids`` — comma-separated list of IDs.

    Example: GET /api/combat/action-outcome-details/?action_interaction_ids=1,2,3

    Effects derived from existing model state — combo upgrade, ConditionInstance
    correlation by source_technique + applied_at window, target status from
    CombatOpponent.status / CharacterVitals.status. No new audit tables.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = OutcomeDetailsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        ids: list[int] = query.validated_data["action_interaction_ids"]

        if not ids:
            return Response([], status=status.HTTP_200_OK)

        details = [_build_outcome_detail(action_id, request.user) for action_id in ids]
        return Response(OutcomeDetailSerializer(details, many=True).data, status=status.HTTP_200_OK)

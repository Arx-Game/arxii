"""Outcome details API for the pose-log expand/collapse UX.

GET /api/combat/action-outcome-details/?action_interaction_ids=N,M,...

Returns a structured list of per-action effects (damage, conditions, etc.)
derived from the mechanical models linked to each ACTION Interaction.

Phase 9, Task 9.4.

v1 note: CombatRoundAction has no direct FK to Interaction yet — there is no
join path from an action_interaction_id to a CombatRoundAction row. Until that
bridge is added, this endpoint returns an empty effects list per action ID. The
frontend renders "No outcome details available." Tracked as §11 item 5 in the
unified-combat-ui plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class EffectRow:
    """A single effect entry in an action's outcome detail."""

    kind: str
    label: str
    deep_link: dict[str, Any] | None


@dataclass
class ActionOutcomeDetail:
    """All effects for one ACTION Interaction."""

    action_interaction_id: int
    effects: list[EffectRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class EffectRowSerializer(serializers.Serializer):
    kind = serializers.CharField()
    label = serializers.CharField()
    deep_link = serializers.DictField(allow_null=True)


class OutcomeDetailSerializer(serializers.Serializer):
    action_interaction_id = serializers.IntegerField()
    effects = EffectRowSerializer(many=True)


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


def _build_outcome_detail(action_interaction_id: int) -> ActionOutcomeDetail:
    """Return the outcome detail for one ACTION Interaction.

    v1: No CombatRoundAction → Interaction join path exists yet. Return empty
    effects. Once the bridge FK is added, walk:
        CombatRoundAction → participant → character_sheet
    and surface ParticipantDamageResult / AppliedConditionResult rows stored
    as related audit models (once those models are added to CombatRoundAction).
    """
    # TODO(phase-9-v2): join via CombatRoundAction when the bridge FK exists.
    return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=[])


class ActionOutcomeDetailsView(APIView):
    """Return outcome details for a list of ACTION Interaction IDs.

    Query parameter: ``action_interaction_ids`` — comma-separated list of IDs.

    Example: GET /api/combat/action-outcome-details/?action_interaction_ids=1,2,3
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        raw_ids = request.query_params.get("action_interaction_ids", "")
        if not raw_ids.strip():
            return Response([], status=status.HTTP_200_OK)

        try:
            ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]
        except ValueError:
            return Response(
                {"detail": "action_interaction_ids must be comma-separated integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        details = [_build_outcome_detail(action_id) for action_id in ids]
        payload = [
            {"action_interaction_id": d.action_interaction_id, "effects": d.effects}
            for d in details
        ]
        serializer = OutcomeDetailSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

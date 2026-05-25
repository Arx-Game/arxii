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

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

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
        query = OutcomeDetailsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        ids: list[int] = query.validated_data["action_interaction_ids"]

        if not ids:
            return Response([], status=status.HTTP_200_OK)

        # TODO(permissions): verify caller can view these action IDs (currently
        # all authenticated users see all effects; gated by empty-effects v1 stub).
        details = [_build_outcome_detail(action_id) for action_id in ids]
        return Response(OutcomeDetailSerializer(details, many=True).data, status=status.HTTP_200_OK)

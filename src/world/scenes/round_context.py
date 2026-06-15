"""Scene (non-combat) implementation of the RoundContext seam."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.round_context import RoundContext
from world.scenes.constants import (
    ACTIVE_SCENE_ROUND_STATUSES,
    RoundStatus,
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
)
from world.scenes.models import SceneActionDeclaration, SceneRoundParticipant

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import SceneRound


class SceneRoundContext(RoundContext):
    """RoundContext backed by a SceneRound the character actively participates in."""

    def __init__(self, scene_round: SceneRound) -> None:
        self._scene_round = scene_round

    @property
    def scene_round(self) -> SceneRound:
        return self._scene_round

    @property
    def round_id(self) -> tuple[int, int]:
        return (self._scene_round.pk, self._scene_round.round_number)

    @property
    def is_declaration_open(self) -> bool:
        # Social (opt-in / GM) rounds gather declarations while DECLARING. DANGER rounds
        # keep the #1046 acute-tier behavior (resolve immediately, tick on action), so they
        # never declaration-gate — this preserves AFK-safety for bleed-out progression.
        return (
            self._scene_round.status == RoundStatus.DECLARING
            and self._scene_round.start_reason != SceneRoundStartReason.DANGER
        )

    @transaction.atomic
    def record_declaration(
        self,
        character: CharacterSheet,
        player_action: Any,
        kwargs: dict[str, Any],  # noqa: ARG002  # contract-mandated; CHALLENGE path ignores it
    ) -> None:
        if not self.is_declaration_open:
            raise ActionDispatchError(ActionDispatchError.ROUND_DECLARATION_CLOSED)
        if player_action.backend != ActionBackend.CHALLENGE:
            # COMBAT never reaches a scene round (combat context precedence). Only CHALLENGE
            # declarations are gathered here; turn-costing REGISTRY is handled in dispatch.
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        from world.mechanics.models import ChallengeApproach, ChallengeInstance  # noqa: PLC0415

        participant = SceneRoundParticipant.objects.get(
            scene_round=self._scene_round,
            character_sheet=character,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        try:
            challenge_instance = ChallengeInstance.objects.get(
                pk=player_action.ref.challenge_instance_id
            )
        except ChallengeInstance.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc
        try:
            challenge_approach = ChallengeApproach.objects.get(pk=player_action.ref.approach_id)
        except ChallengeApproach.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

        SceneActionDeclaration.objects.update_or_create(
            scene_round=self._scene_round,
            round_number=self._scene_round.round_number,
            participant=participant,
            defaults={
                "challenge_instance": challenge_instance,
                "challenge_approach": challenge_approach,
                "is_pass": False,
            },
        )


def resolve_scene_round_context(character: CharacterSheet) -> SceneRoundContext | None:
    """Return a SceneRoundContext for the character's active scene round, or None."""
    participant = (
        SceneRoundParticipant.objects.filter(
            character_sheet=character,
            status=SceneRoundParticipantStatus.ACTIVE,
            scene_round__status__in=ACTIVE_SCENE_ROUND_STATUSES,
        )
        .select_related("scene_round")
        .order_by("-scene_round__created_at")
        .first()
    )
    if participant is None:
        return None
    return SceneRoundContext(participant.scene_round)

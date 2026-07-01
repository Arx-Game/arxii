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
    SceneRoundMode,
    SceneRoundParticipantStatus,
)
from world.scenes.models import SceneActionDeclaration, SceneRoundParticipant

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.mechanics.types import ChallengeResolutionResult
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
        # Only STRICT rounds gather declarations. POSE_ORDER and OPEN rounds resolve
        # immediately. Danger rounds are STRICT, so they gather declarations like any
        # other STRICT round (#1466 — danger is no longer a separate path).
        return (
            self._scene_round.status == RoundStatus.DECLARING
            and self._scene_round.mode == SceneRoundMode.STRICT
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
            is_immediate=False,
            defaults={
                "challenge_instance": challenge_instance,
                "challenge_approach": challenge_approach,
                "is_pass": False,
            },
        )

    def is_repeat_blocked(
        self,
        actor: CharacterSheet,
        action_ref: Any,  # noqa: ARG002
        target_persona: Any,
    ) -> bool:
        from world.scenes.round_services import actions_this_round  # noqa: PLC0415

        rnd = self._scene_round
        if rnd.mode == SceneRoundMode.OPEN:
            return False
        if rnd.mode == SceneRoundMode.STRICT:
            return not self.is_declaration_open
        # POSE_ORDER
        participant = SceneRoundParticipant.objects.get(
            scene_round=rnd,
            character_sheet=actor,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        taken = actions_this_round(rnd, participant)
        if taken >= rnd.max_actions_per_round:
            return True
        if rnd.per_target_repeat_lock and target_persona is not None:
            already_hit = rnd.action_declarations.filter(
                round_number=rnd.round_number,
                participant=participant,
                target_persona=target_persona,
            ).exists()
            if already_hit:
                return True
        return False

    def record_immediate_action(
        self,
        actor: CharacterSheet,
        action_ref: Any,  # noqa: ARG002
        target_persona: Any,
    ) -> None:
        """Write a pose-order ledger row and advance quorum when mode is POSE_ORDER."""
        if self._scene_round.mode != SceneRoundMode.POSE_ORDER:
            return
        from world.scenes.round_services import (  # noqa: PLC0415
            advance_pose_order_round_if_quorum,
            record_pose_order_action,
        )

        participant = SceneRoundParticipant.objects.filter(
            scene_round=self._scene_round,
            character_sheet=actor,
            status=SceneRoundParticipantStatus.ACTIVE,
        ).first()
        if participant is None:
            return
        record_pose_order_action(self._scene_round, participant, target_persona)
        advance_pose_order_round_if_quorum(self._scene_round)

    def get_cover_for(self, target: CharacterSheet, damage_type: Any) -> float:  # noqa: ARG002
        """Resolve (and cache) this round's Succor cover for *target* (#1744).

        Mirrors CombatRoundContext.get_cover_for's caching contract.
        """
        from world.mechanics.reactions import dispatch_capability_reaction  # noqa: PLC0415
        from world.mechanics.succor_shared import (  # noqa: PLC0415
            SUCCOR_CHALLENGE_NAME,
            apply_succor_outcome,
        )

        target_participant = SceneRoundParticipant.objects.filter(
            scene_round=self._scene_round,
            character_sheet=target,
            status=SceneRoundParticipantStatus.ACTIVE,
        ).first()
        if target_participant is None:
            return 1.0

        declaration = SceneActionDeclaration.objects.filter(
            scene_round=self._scene_round,
            round_number=self._scene_round.round_number,
            succor_target=target_participant,
        ).first()
        if declaration is None:
            return 1.0

        if declaration.succor_resolution is not None:
            return declaration.succor_resolution

        succorer = declaration.participant.character_sheet.character
        protected = target_participant.character_sheet.character

        outcome = {"multiplier": 1.0}

        def _capture(result: ChallengeResolutionResult) -> None:
            outcome["multiplier"] = apply_succor_outcome(result)

        result = dispatch_capability_reaction(
            succorer,
            protected,
            challenge_name=SUCCOR_CHALLENGE_NAME,
            approach=None,
            error_msg=f"No succor approach available to {succorer!r} for {protected!r}.",
            outcome_fn=_capture,
        )
        multiplier = outcome["multiplier"] if result is not None else 1.0
        declaration.succor_resolution = multiplier
        declaration.save(update_fields=["succor_resolution"])
        return multiplier


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

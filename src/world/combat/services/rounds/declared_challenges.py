"""Resolving declared challenges at round end."""

from __future__ import annotations

from world.combat.constants import ENTITY_TYPE_PC
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    RoundChallengeDeclaration,
)
from world.mechanics.types import ChallengeResolutionResult


def _resolve_declared_challenges(
    encounter: CombatEncounter,
    round_number: int,
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
) -> list[ChallengeResolutionResult]:
    """Post-pass: resolve RoundChallengeDeclarations in participant initiative order.

    Called after all combat-action resolution for the round.  Fetches bridge rows,
    orders them to match the existing resolution_order for PC participants, resolves
    each character's declared challenge (re-validating eligibility via
    get_available_actions), and deletes all bridge rows for the round.

    Ineligible-skip: if get_available_actions returns no action matching the
    declared (challenge_instance_id, approach_id), the declaration is silently
    skipped — no CharacterChallengeRecord is created and no exception is raised.
    This mirrors dispatch-time security: declared state may be stale if a
    character lost their capability between declaration and resolution.

    The delete of bridge rows runs inside the caller's @transaction.atomic so it
    is consistent with the rest of round resolution.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415
    from world.scenes.round_services import (  # noqa: PLC0415
        ChallengeResolutionRequest,
        resolve_challenge_declarations,
    )
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    declarations = list(
        RoundChallengeDeclaration.objects.filter(
            encounter=encounter,
            round_number=round_number,
        ).select_related(
            "participant",
            "participant__character_sheet",
            "challenge_instance",
            "challenge_instance__location",
            "challenge_approach",
        )
    )

    if not declarations:
        return []

    # Build participant_id → declaration map for O(n) ordering.
    decl_by_participant: dict[int, RoundChallengeDeclaration] = {
        d.participant_id: d for d in declarations
    }

    # Order by the same resolution_order combat uses for PC participants.
    # NPCs never declare challenges, so only ENTITY_TYPE_PC entries matter.
    ordered: list[RoundChallengeDeclaration] = []
    for entity_type, entity in resolution_order:
        if entity_type != ENTITY_TYPE_PC:
            continue
        if not isinstance(entity, CombatParticipant):
            continue
        decl = decl_by_participant.pop(entity.pk, None)
        if decl is not None:
            ordered.append(decl)

    # Any declarations for participants not in resolution_order (e.g. DYING without
    # final-round) come after, preserving their insertion order.
    ordered.extend(decl_by_participant.values())

    # Batched, not one active_persona_for_sheet call per declaration (#4091 fix
    # round 2) -- this builds the whole request list in one comprehension.
    persona_names = persona_names_for_sheets(
        decl.participant.character_sheet_id for decl in ordered
    )
    requests = [
        ChallengeResolutionRequest(
            character=decl.participant.character_sheet.character,
            challenge_instance=decl.challenge_instance,
            approach=decl.challenge_approach,
            actor_label=persona_names.get(
                decl.participant.character_sheet_id,
                decl.participant.character_sheet.character.key,
            ),
        )
        for decl in ordered
    ]
    outcomes = resolve_challenge_declarations(
        requests,
        broadcast=lambda narration: broadcast_action_outcome(
            encounter=encounter, narration=narration
        ),
    )

    # Delete all bridge rows for this round inside the outer atomic block.
    RoundChallengeDeclaration.objects.filter(
        encounter=encounter,
        round_number=round_number,
    ).delete()

    return outcomes

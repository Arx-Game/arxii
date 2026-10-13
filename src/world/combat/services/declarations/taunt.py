"""The taunt social verb."""

from __future__ import annotations

from world.combat.constants import ENTITY_TYPE_PC, CombatManeuver, OpponentStatus, ParticipantStatus
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.declarations.social_check import _social_verb_success_level
from world.combat.services.encounter.threat import accumulate_threat
from world.combat.types import ActionOutcome
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus


def declare_taunt(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a taunting maneuver — draw an NPC's aggro, auto-ready (#2015).

    TAUNT rolls a wits/Persuasion(Intimidation) check at round-tick against the
    target's Composure; on success it accumulates threat on the existing
    ``ThreatRecord`` seam, biasing the NPC's target selection toward the taunter.
    This function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot taunt: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot taunt: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot taunt: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Taunt target must be an active opponent in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.LOW,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.TAUNT,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _resolve_taunt(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared taunt — draw an NPC's aggro (#2015).

    Rolls the Taunt check (wits + Persuasion + Intimidation) against the target's
    Composure. On success, accumulates threat on the existing ThreatRecord seam.
    """
    from world.combat.constants import TAUNT_THREAT_PER_LEVEL  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is not None:
        success_level = _social_verb_success_level(participant, "Taunt", action, target)

        if success_level >= 1:
            accumulate_threat(
                participant.encounter,
                target,
                participant,
                success_level * TAUNT_THREAT_PER_LEVEL,
            )

    return outcome

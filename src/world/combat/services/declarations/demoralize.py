"""The demoralize social verb."""

from __future__ import annotations

from world.combat.constants import ENTITY_TYPE_PC, CombatManeuver, OpponentStatus, ParticipantStatus
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.declarations.social_check import _social_verb_success_level
from world.combat.services.encounter.config import get_social_maneuver_config
from world.combat.types import ActionOutcome
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus


def declare_demoralize(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a demoralizing maneuver — break an opponent's nerve, auto-ready (#2015).

    DEMORALIZE rolls a presence/Persuasion(Intimidation) check at round-tick against
    the target's Composure; on success it depletes the target's morale. Mindless
    opponents resist (not immune). This function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot demoralize: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot demoralize: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot demoralize: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Demoralize target must be an active opponent in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.DEMORALIZE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _resolve_demoralize(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared demoralize — break an opponent's nerve (#2015).

    Rolls the Demoralize check (presence + Persuasion + Intimidation) against the
    target's Composure (+ mindless resistance). On success, depletes morale.
    """
    from world.combat.constants import DEMORALIZE_MORALE_PER_LEVEL  # noqa: PLC0415
    from world.combat.morale import apply_morale_damage, tier_has_morale  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is None:
        return outcome

    success_level = _social_verb_success_level(
        participant, get_social_maneuver_config().demoralize_check_type, action, target
    )

    if success_level < 1:
        # Failed: mindless targets narrate "the construct is unmoved."
        if not tier_has_morale(target):
            outcome.summary = "The construct is unmoved."
        return outcome

    apply_morale_damage(target, success_level * DEMORALIZE_MORALE_PER_LEVEL)
    return outcome

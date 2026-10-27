"""The taunt social verb."""

from __future__ import annotations

from world.combat.constants import (
    ENTITY_TYPE_PC,
    CombatManeuver,
    OpponentStatus,
    ParticipantStatus,
    SurgeTriggerKind,
)
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.declarations.social_check import _social_verb_success_level
from world.combat.services.encounter.config import get_social_maneuver_config
from world.combat.services.encounter.threat import accumulate_threat
from world.combat.surge_rolls import (
    apply_rolled_surge,
    persona_name_of,
    rolled_surge_possible,
    surge_roll_for_participant,
    surge_tuning_for,
)
from world.combat.types import ActionOutcome
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus


def declare_taunt(
    participant: CombatParticipant,
    target: CombatOpponent | CombatParticipant,
) -> CombatRoundAction:
    """Declare a taunting maneuver, auto-ready (#2015, #4737).

    Against an opponent, TAUNT rolls a wits/Persuasion(Intimidation) check at round-tick
    against the target's Composure; on success it accumulates threat on the existing
    ``ThreatRecord`` seam, biasing the NPC's target selection toward the taunter.
    Against another player character it stores the target on ``focused_ally_target`` and
    the resolution turns the taunter's check rating into a potency the target rolls Composure
    against (a rolled surge, #4737). This function only records the declaration, and
    refuses nothing a taunted player character later declares.
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

    opponent_target: CombatOpponent | None = None
    ally_target: CombatParticipant | None = None
    if isinstance(target, CombatParticipant):
        if target.pk == participant.pk:
            msg = "Cannot taunt yourself."
            raise ValueError(msg)
        if target.encounter_id != encounter.pk or target.status != ParticipantStatus.ACTIVE:
            msg = "Taunt target must be an active participant in this encounter."
            raise ValueError(msg)
        if is_dead(target.character_sheet):
            msg = "Cannot taunt: the target is dead."
            raise ValueError(msg)
        ally_target = target
    else:
        if target.encounter_id != encounter.pk or target.status != OpponentStatus.ACTIVE:
            msg = "Taunt target must be an active opponent in this encounter."
            raise ValueError(msg)
        opponent_target = target

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.LOW,
            "focused_opponent_target": opponent_target,
            "focused_ally_target": ally_target,
            "maneuver": CombatManeuver.TAUNT,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _resolve_taunt_on_participant(
    participant: CombatParticipant,
    target: CombatParticipant,
) -> None:
    """A player character taunts another: the taunter's check rating is the potency (#4737).

    The potency is the taunter's check RATING for the Taunt check type (no dice, nothing
    spent for the taunter: the player character who is taunted is the one who rolls). The
    target then rolls the tuned check (Composure) against that potency, and the roll's
    degree picks the surge band. A target who left the encounter or died since the
    declaration, an encounter with no escalation curve, an unset or inactive Taunt check
    designation or a missing tuning,
    and a target who could not surge this round (no combat engagement, or already surged by
    this taunter) are all quiet no-ops: no roll is made and no condition is spent.
    """
    from world.checks.services import compute_check_rating  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if (
        encounter.escalation_curve is None
        or target.status != ParticipantStatus.ACTIVE
        or is_dead(target.character_sheet)
    ):
        return
    tuning = surge_tuning_for(SurgeTriggerKind.TAUNT_RECEIVED)
    # The taunter's own check is designated on SocialManeuverConfig (#4739); the tuning's
    # check is the target's composure. An unset designation is listed on the dashboard.
    taunt_check = get_social_maneuver_config().taunt_check_type
    if tuning is None or taunt_check is None or not taunt_check.is_active:
        return
    if not rolled_surge_possible(
        encounter, target, SurgeTriggerKind.TAUNT_RECEIVED, participant.character_sheet
    ):
        return

    # A rating can be negative; the stored potency is unsigned.
    potency = max(0, compute_check_rating(participant.character_sheet.character, taunt_check))
    result = surge_roll_for_participant(target, tuning.check_type, potency)
    apply_rolled_surge(
        encounter=encounter,
        participant=target,
        trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED,
        outcome=result.outcome,
        potency=potency,
        subject_sheet=participant.character_sheet,
        source_character=participant.character_sheet.character,
        tuning=tuning,
        cause=f"{persona_name_of(participant)} taunts {persona_name_of(target)}.",
    )


def _resolve_taunt(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared taunt (#2015, #4737).

    Against an opponent: rolls the Taunt check (wits + Persuasion + Intimidation) against
    the target's Composure and, on success, accumulates threat on the existing
    ThreatRecord seam. Against a player character: a rolled surge, see
    ``_resolve_taunt_on_participant``.
    """
    from world.combat.constants import TAUNT_THREAT_PER_LEVEL  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is not None:
        success_level = _social_verb_success_level(
            participant, get_social_maneuver_config().taunt_check_type, action, target
        )

        if success_level >= 1:
            accumulate_threat(
                participant.encounter,
                target,
                participant,
                success_level * TAUNT_THREAT_PER_LEVEL,
            )
    elif action.focused_ally_target is not None:
        _resolve_taunt_on_participant(participant, action.focused_ally_target)

    return outcome

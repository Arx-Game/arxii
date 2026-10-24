"""Declaring a waiting strike (#4608, slice 3 of #4576).

The waiting strike is a PC's one action for the round: a melee technique held for an
enemy that comes into reach or attacks. It fires at most once, through
``world.combat.services.rounds.waiting_strikes``; in the PC's own resolution slot the
row does nothing. Costs are charged only when it fires.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.models import CombatParticipant, CombatRoundAction
from world.combat.types import ActionOutcome
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.magic.models import Technique

_ERR_CANNOT_ACT = "You cannot act this round."
_ERR_NOT_DECLARING = "You can only wait for an opening while the round is being declared."
_ERR_NOT_MELEE = "A waiting strike needs a strike that reaches your own position or the next."
_ERR_NOT_SINGLE = "A waiting strike needs a strike at one enemy."
_ERR_UNKNOWN = "You do not know that technique."
_ERR_NOT_COMBAT_READY = "That technique cannot be used in a fight."


def _melee_reaches() -> tuple[str, ...]:
    from world.magic.constants import TechniqueReach  # noqa: PLC0415

    return (TechniqueReach.SAME, TechniqueReach.ADJACENT)


def validate_waiting_strike_technique(participant: CombatParticipant, technique: Technique) -> None:
    """Raise ValueError unless ``technique`` can be held as a waiting strike.

    It must be known, combat-ready (an action template and a cast check), aimed at one
    target, and melee: reach SAME or ADJACENT.
    """
    from actions.constants import ActionTargetType  # noqa: PLC0415
    from world.magic.models import CharacterTechnique  # noqa: PLC0415
    from world.magic.services.magic_skills import resolve_cast_check  # noqa: PLC0415

    sheet = participant.character_sheet
    if not CharacterTechnique.objects.filter(character=sheet, technique=technique).exists():
        raise ValueError(_ERR_UNKNOWN)
    if technique.reach not in _melee_reaches():
        raise ValueError(_ERR_NOT_MELEE)
    if technique.target_type != ActionTargetType.SINGLE:
        raise ValueError(_ERR_NOT_SINGLE)
    if technique.action_template_id is None:
        raise ValueError(_ERR_NOT_COMBAT_READY)
    if resolve_cast_check(sheet.character, technique) is None:
        raise ValueError(_ERR_NOT_COMBAT_READY)


def declare_await_opening(
    participant: CombatParticipant,
    technique: Technique,
    *,
    confirm_soulfray_risk: bool = False,
) -> CombatRoundAction:
    """Declare a waiting strike with ``technique`` for the current round.

    Same row shape as ``declare_charge``: ``maneuver=AWAIT_OPENING``,
    ``focused_action=technique`` and no opponent target. The target is written only
    when the strike fires (it is the enemy struck), so ``focused_opponent_target`` being
    set is what "fired" means; nothing else is stored. Replaces any other declaration
    this round, as every declaration does: the waiting strike is the PC's one action.

    ``confirm_soulfray_risk`` records consent to cast into Soulfray, as for any cast;
    without it a strike that would need Soulfray lapses when it fires.

    Raises ValueError with a player-facing message when the strike cannot be declared.
    """
    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter
    if participant.status != ParticipantStatus.ACTIVE or not can_act(participant.character_sheet):
        raise ValueError(_ERR_CANNOT_ACT)
    if encounter.status != RoundStatus.DECLARING:
        raise ValueError(_ERR_NOT_DECLARING)
    validate_waiting_strike_technique(participant, technique)

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": technique.action_category,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": None,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.AWAIT_OPENING,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "confirm_soulfray_risk": confirm_soulfray_risk,
            "is_ready": False,
        },
    )
    # Extra AoE targets from an earlier declaration this round do not carry over.
    action.extra_targets.all().delete()
    return action


def _resolve_await_opening(
    participant: CombatParticipant, action: CombatRoundAction
) -> ActionOutcome:
    """The waiting strike's own resolution slot: nothing happens here.

    The strike fires, at most once, from ``fire_waiting_strikes`` when an enemy arrives
    in reach or attacks; a strike that never fires costs nothing but the action.
    """
    from world.combat.constants import ENTITY_TYPE_PC  # noqa: PLC0415

    del action
    return ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

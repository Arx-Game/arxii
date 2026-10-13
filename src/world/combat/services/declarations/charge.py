"""Declaring a charge and resolving its movement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CHARGE_MAX_HOPS, CombatManeuver, OpponentStatus
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.magic.models import Technique


def declare_charge(
    participant: CombatParticipant,
    technique: Technique,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a mounted charge — closes distance to *opponent*, then attacks (#1843).

    Validations:
    - Participant must be able to act and the encounter must be DECLARING.
    - The rider must hold the Mounted condition
      (``world.companions.mount_content.MOUNTED_CONDITION_NAME``).
    - *opponent* must be ACTIVE.
    - *opponent*'s position must be at least 1 hop from the rider's current
      position AND reachable within ``CHARGE_MAX_HOPS``. Lenient (allowed)
      when either combatant is unpositioned — mirrors
      ``technique_can_reach``'s leniency (``world/combat/reach.py``).

    Resolution (``_resolve_pc_action``) moves the rider onto *opponent*'s
    position (``force_move_to_position``), then falls through to the normal
    weapon-attack pipeline — ``CombatTechniqueResolver`` folds
    ``CHARGE_CHECK_BONUS``/``CHARGE_DAMAGE_BONUS`` into the check/damage
    (doubled when the equipped weapon is a LANCE). The attack always runs
    through the normal (non-bypassing) damage pipeline — defenses, guardians,
    and ramparts fire exactly as they would for any other attack.

    Raises ValueError with clear messages for validation failures.
    """
    from world.areas.positioning.services import position_of, position_reachable  # noqa: PLC0415
    from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import has_condition  # noqa: PLC0415
    from world.magic.constants import TechniqueReach  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter
    if not can_act(participant.character_sheet):
        msg = "Cannot charge: character is dead or incapacitated."
        raise ValueError(msg)
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot charge: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if opponent.status != OpponentStatus.ACTIVE:
        msg = "Cannot charge a defeated opponent."
        raise ValueError(msg)

    mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
    if not has_condition(participant.character_sheet.character, mounted_template):
        msg = "Cannot charge: you must be mounted."
        raise ValueError(msg)

    rider_pos = position_of(participant.character_sheet.character)
    target_pos = position_of(opponent.objectdb) if opponent.objectdb is not None else None
    if rider_pos is not None and target_pos is not None:
        if rider_pos.pk == target_pos.pk:
            msg = "Cannot charge: the target is already within reach."
            raise ValueError(msg)
        if not position_reachable(
            rider_pos, target_pos, TechniqueReach.REACH_N, reach_hops=CHARGE_MAX_HOPS
        ):
            msg = "Cannot charge: the target is not reachable."
            raise ValueError(msg)

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": technique.action_category,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.CHARGE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": False,
        },
    )
    return action


def _resolve_charge_movement(participant: CombatParticipant, action: CombatRoundAction) -> None:
    """Move *participant*'s character onto the CHARGE target's position (#1843).

    Called unconditionally at resolution time — reachability was already
    validated at declaration (``declare_charge``), but the round may have
    moved other combatants since; force-moving unconditionally here mirrors
    the existing Guardian blink-protect call site
    (``world.areas.positioning.services.force_move_to_position``) rather than
    re-validating and potentially fizzling a declared charge on a stale check.
    No-ops when either side is unpositioned (lenient, matches declare-time).
    """
    from world.areas.positioning.services import (  # noqa: PLC0415
        force_move_to_position,
        position_of,
    )

    target = action.focused_opponent_target
    if target is None or target.objectdb is None:
        return
    dest = position_of(target.objectdb)
    if dest is None:
        return
    rider = participant.character_sheet.character
    if position_of(rider) is None:
        return
    force_move_to_position(rider, dest)

"""Standoff state: opening one, the groups in it, and breaking it into a fight."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import OpponentStatus
from world.standoffs.constants import StandoffGroupState
from world.standoffs.models import StandoffGroup

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter, CombatOpponent


def is_in_standoff(encounter: CombatEncounter) -> bool:
    """A standoff is the stretch before round one with a group still OPEN."""
    if encounter.round_number != 0:
        return False
    return StandoffGroup.objects.filter(encounter=encounter, state=StandoffGroupState.OPEN).exists()


def open_standoff(encounter: CombatEncounter) -> list[StandoffGroup]:
    """One OPEN group per creature template among the active opponents, then check causes."""
    template_ids = {
        opponent.creature_template_id
        for opponent in encounter.opponents.filter(status=OpponentStatus.ACTIVE)
        if opponent.creature_template_id is not None
    }
    groups = [
        StandoffGroup.objects.create(encounter=encounter, creature_template_id=template_id)
        for template_id in sorted(template_ids)
    ]
    if groups:
        from world.standoffs.services.force import evaluate_causes  # noqa: PLC0415

        evaluate_causes(encounter)
    return groups


def active_members(group: StandoffGroup) -> list[CombatOpponent]:
    """The group's opponents still in the fight."""
    return list(
        group.encounter.opponents.filter(
            creature_template_id=group.creature_template_id, status=OpponentStatus.ACTIVE
        )
    )


def settle_empty_groups(encounter: CombatEncounter) -> None:
    """An OPEN group with nobody left standing is SETTLED."""
    for group in encounter.standoff_groups.filter(state=StandoffGroupState.OPEN):
        if not active_members(group):
            group.state = StandoffGroupState.SETTLED
            group.save(update_fields=["state"])


def end_standoff_into_fight(encounter: CombatEncounter, *, initiated_by_pc_side: bool) -> None:
    """Every OPEN group goes to FIGHTING and round one begins."""
    from world.combat.services import begin_declaration_phase  # noqa: PLC0415

    for group in encounter.standoff_groups.filter(state=StandoffGroupState.OPEN):
        group.state = StandoffGroupState.FIGHTING
        group.save(update_fields=["state"])
    encounter.initiated_by_pc_side = initiated_by_pc_side
    encounter.save(update_fields=["initiated_by_pc_side"])
    begin_declaration_phase(encounter)

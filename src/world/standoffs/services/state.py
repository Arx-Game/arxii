"""Standoff state: opening one, the groups in it, and breaking it into a fight."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

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


@transaction.atomic
def end_standoff_into_fight(
    encounter: CombatEncounter, *, initiated_by_pc_side: bool | None
) -> bool:
    """Every OPEN group goes to FIGHTING and round one begins.

    Locks the encounter row first and rechecks, so when two things break the standoff at
    once only the first writes; the second returns False and changes nothing.
    """
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.combat.services import begin_declaration_phase  # noqa: PLC0415

    locked = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if not is_in_standoff(locked):
        return False
    for group in encounter.standoff_groups.filter(state=StandoffGroupState.OPEN):
        group.state = StandoffGroupState.FIGHTING
        group.save(update_fields=["state"])
    encounter.initiated_by_pc_side = initiated_by_pc_side
    encounter.save(update_fields=["initiated_by_pc_side"])
    begin_declaration_phase(encounter)
    return True


def begin_round_or_break_standoff(
    encounter: CombatEncounter, *, initiated_by_pc_side: bool | None
) -> None:
    """Start a round; if the encounter is still in its standoff, that breaks the standoff."""
    from world.combat.services import begin_declaration_phase  # noqa: PLC0415

    if is_in_standoff(encounter):
        end_standoff_into_fight(encounter, initiated_by_pc_side=initiated_by_pc_side)
    else:
        begin_declaration_phase(encounter)

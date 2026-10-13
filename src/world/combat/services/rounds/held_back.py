"""Narration for a held-back action."""

from __future__ import annotations

from world.combat.constants import ENTITY_TYPE_PC, HELD_BACK_NARRATION, PaceMode
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.npc.narration import _dual_dispatch_combat_narration


def _narrate_held_back(
    encounter: CombatEncounter,
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
    pc_actions: dict[int, CombatRoundAction],
    sustaining_participant_ids: frozenset[int],
) -> None:
    """Name every PC the resolve loop skipped for having declared nothing (#3552).

    Only under TIMED and MANUAL pace: READY cannot resolve until every ACTIVE
    participant has readied a ``CombatRoundAction``, so a silent skip is
    impossible there. A participant who declared a ``SustainedAction`` this
    round is committing, not holding back.
    """
    if encounter.pace_mode not in (PaceMode.TIMED, PaceMode.MANUAL):
        return
    for entity_type, entity in resolution_order:
        if entity_type != ENTITY_TYPE_PC or not isinstance(entity, CombatParticipant):
            continue
        if entity.pk in sustaining_participant_ids or entity.pk in pc_actions:
            continue
        name = str(entity.character_sheet.character)
        _dual_dispatch_combat_narration(encounter, HELD_BACK_NARRATION.format(name=name))

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
    held = [
        entity
        for entity_type, entity in resolution_order
        if entity_type == ENTITY_TYPE_PC
        and isinstance(entity, CombatParticipant)
        and entity.pk not in sustaining_participant_ids
        and entity.pk not in pc_actions
    ]
    if not held:
        return
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    # The face the character presents, as every other round line names them (never the key).
    names = persona_names_for_sheets(p.character_sheet_id for p in held)
    for participant in held:
        name = names.get(participant.character_sheet_id, participant.character_sheet.character.key)
        _dual_dispatch_combat_narration(encounter, HELD_BACK_NARRATION.format(name=name))

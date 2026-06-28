"""Derived-on-read NPC allegiance (#1590, ADR-0058, ADR-0014).

Allegiance is NOT a stored column — it is derived from the opponent's active
``alters_behavior`` conditions (charm/calm) at read time. A charmed NPC fights
for the charmer's side; a calmed NPC holds (will not attack). The combat
target-selection consults this so a charmed NPC skips the caster's party.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.constants import (
    CALM_CONDITION_NAME,
    CHARM_CONDITION_NAME,
    Allegiance,
)
from world.conditions.services import get_active_conditions

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter, CombatOpponent


def derive_allegiance(
    opponent: CombatOpponent,
    encounter: CombatEncounter,  # noqa: ARG001 — reserved for future party lookup
) -> Allegiance:
    """Return the opponent's current allegiance (derived, not stored)."""
    if opponent.objectdb_id is None:
        return Allegiance.ENEMY
    active = list(get_active_conditions(opponent.objectdb))
    names = {inst.condition.name for inst in active}
    if CHARM_CONDITION_NAME in names:
        # Charm wins over calm (stronger compulsion). Source-character
        # validation (charmer is a live PC participant) is the caller's job;
        # here we trust the condition's presence.
        return Allegiance.ALLY_OF_CASTER
    if CALM_CONDITION_NAME in names:
        return Allegiance.NEUTRAL
    return Allegiance.ENEMY

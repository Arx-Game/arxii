"""Positional reach predicate for combat technique targeting (Task 3 / #533).

Wraps position_reachable with leniency for unpositioned rooms and combatants.
A LATER task wires this into declare-time validation — do NOT call from services yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.areas.positioning.services import position_of, position_reachable

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import Technique


def technique_can_reach(attacker: ObjectDB, technique: Technique, target: ObjectDB) -> bool:
    """Return True if ``attacker`` can reach ``target`` with ``technique``.

    Lenient when positioning is absent: if EITHER combatant has no Position
    (room has no positioning graph, or combatant unplaced), return True — do
    not block combat in unpositioned rooms (matches the lenient behavior of
    _positioning_actions). Otherwise delegate to position_reachable(origin,
    target_pos, technique.reach).
    """
    attacker_pos = position_of(attacker)
    if attacker_pos is None:
        return True

    target_pos = position_of(target)
    if target_pos is None:
        return True

    return position_reachable(attacker_pos, target_pos, technique.reach)

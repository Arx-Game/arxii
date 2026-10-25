"""How a player character crosses the position graph, from her capabilities (#4663).

An NPC's traversal is one authored ``CreatureTraversal`` on its profile. A player
character's is derived: every character walks, and each ``CapabilityType`` that carries a
``traversal`` adds that way of moving once the character's effective value of it is above
its innate baseline (a species gift, a distinction, a technique grant or a condition can
all raise it). A character can hold several at once, so a crossing costs the cheapest of
them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.services import edge_crossing_cost

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import PositionEdge
    from world.character_sheets.models import CharacterSheet

WALKING_ONLY: frozenset[str] = frozenset({CreatureTraversal.WALKS})


def player_traversals(sheet: CharacterSheet) -> frozenset[str]:
    """Every ``CreatureTraversal`` the character can use: WALKS, plus each one a capability
    she holds above its innate baseline carries."""
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

    traversals = set(WALKING_ONLY)
    for capability in CapabilityType.objects.exclude(traversal=""):
        if capability.traversal in traversals:
            continue
        if get_effective_capability_value(sheet, capability) > capability.innate_baseline:
            traversals.add(capability.traversal)
    return frozenset(traversals)


def traversals_of(objectdb: ObjectDB) -> frozenset[str]:
    """``player_traversals`` for a character with a sheet; anything else only walks."""
    try:
        sheet = objectdb.sheet_data
    except AttributeError:
        # RelatedObjectDoesNotExist subclasses AttributeError: no sheet.
        return WALKING_ONLY
    return player_traversals(sheet)


def cheapest_crossing(edge: PositionEdge, traversals: frozenset[str]) -> tuple[int, str] | None:
    """The fewest hops any of ``traversals`` pays to cross ``edge``, and which one pays it.

    None when ``edge`` is shut to all of them. Ties go to the ``CreatureTraversal``
    declared first, so a climber-leaper climbs.
    """
    best: tuple[int, int, str] | None = None
    order = list(CreatureTraversal.values)
    for traversal in traversals:
        cost = edge_crossing_cost(edge, traversal)
        if cost is None:
            continue
        candidate = (cost, order.index(traversal), traversal)
        if best is None or candidate < best:
            best = candidate
    return None if best is None else (best[0], best[2])


def best_crossing_cost(edge: PositionEdge, traversals: frozenset[str]) -> int | None:
    """The fewest hops any of ``traversals`` pays to cross ``edge``; None when all are shut."""
    crossing = cheapest_crossing(edge, traversals)
    return None if crossing is None else crossing[0]

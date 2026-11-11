"""How a player character moves and dodges, from the applications her sources match (#5066).

An NPC's traversal is one authored ``CreatureTraversal`` on its profile. A player
character's comes from the four layers (``docs/architecture/property-capability-action.md``):
each of her capability sources (a technique grant, trained ability, a condition, a species
gift or distinction) is matched against every ``Application`` that says something about
moving (``Application.way_of_moving`` / ``dodges``), by ``source_matches_application``: the
same capability, held above its innate baseline, carrying the mark the application needs.
A technique's marks are its own ``Technique.properties``, so a technique marked ``teleport``
that grants ``traversal`` reaches a "Blink" application on any gift; nobody authors a blink
capability.

Every character walks. Each matched application without ``dodges`` adds its way of moving
for her turn; one with ``dodges`` lets her dodge attacks automatically
(``world.combat.services.reactions``). A crossing costs the cheapest of her ways.

How far one use reaches is set by its strength through one shared set of bands
(``MovementConfig.reach_*_at``, ``reach_for_strength``). A technique use's strength comes
from its cast roll (``world.combat.services.movement_use``); any other source's is its
value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.areas.positioning.constants import CreatureTraversal, ReactionReach
from world.areas.positioning.services import edge_crossing_cost
from world.mechanics.constants import CapabilitySourceType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import PositionEdge
    from world.character_sheets.models import CharacterSheet
    from world.mechanics.models import Application
    from world.mechanics.types import CapabilitySource

WALKING_ONLY: frozenset[str] = frozenset({CreatureTraversal.WALKS})


@dataclass(frozen=True)
class MovementSource:
    """One of her capability sources reaching one movement application (#5066)."""

    source: CapabilitySource
    application: Application

    @property
    def way(self) -> str:
        """The way of moving the application gives (blank: in place or by walking)."""
        return self.application.way_of_moving

    @property
    def standing_strength(self) -> int:
        """The source's value: its strength before any roll (a technique's standing grant)."""
        return self.source.value

    @property
    def technique_id(self) -> int | None:
        """The granting technique's pk when the source is a technique, else None."""
        if self.source.source_type == CapabilitySourceType.TECHNIQUE:
            return self.source.source_id
        return None

    @property
    def name(self) -> str:
        """The source's own name (a technique's, a condition's), or the application's."""
        return self.source.source_name or self.application.name


def movement_applications() -> list[Application]:
    """Every application that says something about moving: a way of moving or a dodge."""
    from django.db.models import Q  # noqa: PLC0415

    from world.mechanics.models import Application  # noqa: PLC0415

    return list(
        Application.objects.filter(Q(dodges=True) | ~Q(way_of_moving=""))
        .select_related("capability", "target_property", "required_effect_property")
        .order_by("pk")
    )


def matched_movement(objectdb: ObjectDB) -> list[MovementSource]:
    """Every (source, movement application) pair she reaches, strongest source first.

    Nothing for an object with no capability sources. Ties keep the sources' own order
    (techniques first), then the application's pk.
    """
    from world.mechanics.services import (  # noqa: PLC0415
        get_capability_sources_for_character,
        source_matches_application,
    )

    applications = movement_applications()
    if not applications:
        return []
    capability_ids = {app.capability_id for app in applications}
    sources = [
        source
        for source in get_capability_sources_for_character(objectdb)
        if source.capability_id in capability_ids
    ]
    matched = [
        MovementSource(source=source, application=app)
        for source in sources
        for app in applications
        if source_matches_application(source, app)
    ]
    matched.sort(key=lambda ms: -ms.standing_strength)
    return matched


def player_traversals(sheet: CharacterSheet) -> frozenset[str]:
    """Every ``CreatureTraversal`` she can use on her turn: WALKS, plus the way of moving of
    each turn-move application (one without ``dodges``) some source of hers matches."""
    return traversals_from(matched_movement(sheet.character))


def traversals_from(matched: list[MovementSource]) -> frozenset[str]:
    """WALKS plus the turn-move ways in ``matched``."""
    ways = {ms.way for ms in matched if ms.way and not ms.application.dodges}
    return frozenset(WALKING_ONLY | ways)


def traversals_of(objectdb: ObjectDB) -> frozenset[str]:
    """``player_traversals`` for a character with a sheet; anything else only walks."""
    try:
        sheet = objectdb.sheet_data
    except AttributeError:
        # RelatedObjectDoesNotExist subclasses AttributeError: no sheet.
        return WALKING_ONLY
    return player_traversals(sheet)


def turn_movement_sources(objectdb: ObjectDB, way: str) -> list[MovementSource]:
    """Her sources that move ``way`` on her turn, strongest first; one per source."""
    try:
        objectdb.sheet_data  # noqa: B018 - only player characters move by their powers
    except AttributeError:
        return []
    seen: set[tuple[str, int, int]] = set()
    found: list[MovementSource] = []
    for ms in matched_movement(objectdb):
        if ms.application.dodges or ms.way != way:
            continue
        key = (ms.source.source_type, ms.source.source_id, ms.source.capability_id)
        if key in seen:
            continue
        seen.add(key)
        found.append(ms)
    return found


def reach_for_strength(strength: int) -> str:
    """How far one use of this strength may take her, by the shared bands (#5066).

    Below ``MovementConfig.reach_neighbour_at`` she stays in place; then a neighbouring
    place, two places away, anywhere in the room. The same bands for every movement power,
    for a dodge's landing and a turn move alike. Field defaults when no config row exists.
    """
    from world.combat.models import MovementConfig  # noqa: PLC0415

    row = MovementConfig.objects.cached_singleton() or MovementConfig()
    if strength >= row.reach_anywhere_at:
        return ReactionReach.ANY_PLACE
    if strength >= row.reach_two_places_at:
        return ReactionReach.TWO_PLACES
    if strength >= row.reach_neighbour_at:
        return ReactionReach.ADJACENT
    return ReactionReach.IN_PLACE


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

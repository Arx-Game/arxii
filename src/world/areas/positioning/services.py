"""Authoring, query, and movement services for the positioning system.

Phase 1: positions + edges are room-anchored; gated edges block crossing
(full cross-via-approach resolution is deferred to Phase 2).
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from django.db.models import Q

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.exceptions import PositionError, PositionTransitionError
from world.areas.positioning.models import ObjectPosition, Position, PositionEdge

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.mechanics.models import ChallengeInstance


# ---------------------------------------------------------------------------
# Authoring / mutation
# ---------------------------------------------------------------------------


def create_position(
    room: ObjectDB,
    name: str,
    *,
    kind: str = PositionKind.FEATURE,
    description: str = "",
) -> Position:
    """Create and return a new Position in the given room."""
    return Position.objects.create(room=room, name=name, kind=kind, description=description)


def remove_position(position: Position) -> None:
    """Delete a position (cascades to edges and occupancy rows)."""
    position.delete()


def connect_positions(
    a: Position,
    b: Position,
    *,
    is_passable: bool = True,
    gating_challenge: ChallengeInstance | None = None,
) -> PositionEdge:
    """Create a traversable edge between two positions, ordered canonically.

    The smaller-pk position becomes position_a (canonical ordering).
    Calls full_clean() before save so cross-room / self-loop constraints fire.
    """
    if a.pk > b.pk:
        a, b = b, a
    edge = PositionEdge(
        position_a=a,
        position_b=b,
        is_passable=is_passable,
        gating_challenge=gating_challenge,
    )
    edge.full_clean()
    edge.save()
    return edge


def disconnect_positions(a: Position, b: Position) -> None:
    """Remove the edge between two positions (order-independent)."""
    lo, hi = (a, b) if a.pk < b.pk else (b, a)
    PositionEdge.objects.filter(position_a=lo, position_b=hi).delete()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def edge_between(a: Position, b: Position) -> PositionEdge | None:
    """Return the edge between two positions, regardless of argument order."""
    lo, hi = (a, b) if a.pk < b.pk else (b, a)
    return (
        PositionEdge.objects.filter(position_a=lo, position_b=hi)
        .select_related("gating_challenge__template")
        .first()
    )


def position_of(objectdb: ObjectDB) -> Position | None:
    """Return the Position currently occupied by objectdb, or None."""
    try:
        return objectdb.object_position.position
    except ObjectPosition.DoesNotExist:
        return None


def _passable_open_edges(position: Position) -> list[PositionEdge]:
    """Return edges touching *position* that are passable and unblocked.

    An edge is blocked only by an ACTIVE gating challenge; an edge whose gating
    challenge is inactive (or absent) is freely crossable. Fetches all touching
    edges in one query (no queries in loops).
    """
    edges = (
        PositionEdge.objects.filter(
            Q(position_a=position) | Q(position_b=position),
            is_passable=True,
        )
        .exclude(
            gating_challenge__isnull=False,
            gating_challenge__is_active=True,
        )
        .select_related("position_a", "position_b", "gating_challenge")
    )
    return list(edges)


def reachable_positions(objectdb: ObjectDB) -> set[Position]:
    """Return the set of positions reachable from objectdb's current position.

    Multi-hop BFS over passable edges. Edges blocked by an ACTIVE gating
    challenge are not crossed; edges with no gating challenge or an inactive
    one are freely traversable. The starting position is not included.
    """
    start = position_of(objectdb)
    if start is None:
        return set()
    seen: set[int] = {start.pk}
    frontier: deque[Position] = deque([start])
    result: set[Position] = set()
    while frontier:
        current = frontier.popleft()
        for edge in _passable_open_edges(current):
            other = edge.position_b if edge.position_a_id == current.pk else edge.position_a
            if other.pk not in seen:
                seen.add(other.pk)
                result.add(other)
                frontier.append(other)
    return result


# ---------------------------------------------------------------------------
# Character-sheet resolution
# ---------------------------------------------------------------------------


def _character_sheet_of(objectdb: ObjectDB) -> CharacterSheet | None:
    """Return the CharacterSheet for objectdb if it is a character, else None.

    Uses the related_name "sheet_data" on CharacterSheet.character (OneToOne→ObjectDB).
    Non-character objects have no sheet_data; we return None so callers can skip
    the MOVEMENT gate.
    """
    from world.character_sheets.models import CharacterSheet

    try:
        return objectdb.sheet_data
    except CharacterSheet.DoesNotExist:
        return None


def _can_move(objectdb: ObjectDB) -> bool:
    """Return True if objectdb has MOVEMENT capability > 0 (or is not a character).

    Lets CapabilityType.DoesNotExist propagate — MOVEMENT is authored content
    and must exist at game-start; a missing entry is a fatal configuration error.
    """
    from world.conditions.constants import FoundationalCapability
    from world.conditions.models import CapabilityType
    from world.conditions.services import get_effective_capability_value

    sheet = _character_sheet_of(objectdb)
    if sheet is None:
        return True  # non-character objects are always movable
    movement: CapabilityType = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
    return get_effective_capability_value(sheet, movement) > 0


# ---------------------------------------------------------------------------
# Placement + movement
# ---------------------------------------------------------------------------


_ERR_PLACE_CROSS_ROOM = "That position is not in the same room as the object."
_ERR_MOVE_CROSS_ROOM = "That position is not in this room."
_ERR_MOVE_UNPLACED = "You are not placed in any position yet."
_ERR_MOVE_NO_PATH = "There is no path to there."
_ERR_MOVE_BLOCKED = "The way is blocked."
_ERR_MOVE_IMMOBILE = "You cannot move."


def place_in_position(objectdb: ObjectDB, position: Position) -> ObjectPosition:
    """Place objectdb in position (setup / staff teleport).

    Raises PositionError if position.room != objectdb.location.
    Uses update_or_create so calling twice is idempotent (updates occupancy).
    """
    if position.room_id != objectdb.db_location_id:
        raise PositionError(_ERR_PLACE_CROSS_ROOM)
    obj_pos, _ = ObjectPosition.objects.update_or_create(
        objectdb=objectdb,
        defaults={"position": position},
    )
    return obj_pos


def move_to_position(objectdb: ObjectDB, target: Position) -> ObjectPosition:
    """Voluntary move from current position to target position.

    Validation order (each failure raises PositionTransitionError):
    1. target is in the same room as objectdb
    2. objectdb is currently placed in a position
    3. an edge exists between current and target
    4. the edge is passable
    5. the edge has no active gating challenge
    6. the actor's MOVEMENT capability > 0 (characters only)
    """
    if target.room_id != objectdb.db_location_id:
        raise PositionTransitionError(_ERR_MOVE_CROSS_ROOM)

    current = position_of(objectdb)
    if current is None:
        raise PositionTransitionError(_ERR_MOVE_UNPLACED)

    edge = edge_between(current, target)
    if edge is None:
        raise PositionTransitionError(_ERR_MOVE_NO_PATH)

    if not edge.is_passable:
        raise PositionTransitionError(_ERR_MOVE_BLOCKED)

    if edge.gating_challenge_id is not None and edge.gating_challenge.is_active:
        challenge_name = edge.gating_challenge.template.name
        msg = f"Crossing that requires getting past {challenge_name}."
        raise PositionTransitionError(msg)

    if not _can_move(objectdb):
        raise PositionTransitionError(_ERR_MOVE_IMMOBILE)

    obj_pos, _ = ObjectPosition.objects.update_or_create(
        objectdb=objectdb,
        defaults={"position": target},
    )
    return obj_pos


def force_move_to_position(objectdb: ObjectDB, target: Position) -> ObjectPosition:
    """Move objectdb to target, bypassing capability + gate checks.

    Only requires same room. No edge required.
    """
    if target.room_id != objectdb.db_location_id:
        raise PositionError(_ERR_PLACE_CROSS_ROOM)
    obj_pos, _ = ObjectPosition.objects.update_or_create(
        objectdb=objectdb,
        defaults={"position": target},
    )
    return obj_pos

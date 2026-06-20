"""Authoring, query, and movement services for the positioning system.

Phase 1: positions + edges are room-anchored; gated edges block crossing
(full cross-via-approach resolution is deferred to Phase 2).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db.models import Q

from world.areas.positioning.constants import AERIAL_PROPERTY_NAME, PositionKind
from world.areas.positioning.exceptions import PositionError, PositionTransitionError
from world.areas.positioning.models import (
    BlueprintEdge,
    BlueprintPosition,
    ObjectPosition,
    Position,
    PositionBlueprint,
    PositionEdge,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.mechanics.models import ChallengeInstance


@dataclass(frozen=True)
class PositionAdjacency:
    """Adjacency entry for a single position under ADJACENT-reach semantics.

    ``adjacent_position_ids`` contains every position reachable from
    ``position_id`` via a single passable edge, regardless of gating
    challenges (matching ``position_reachable``'s ADJACENT semantics:
    gating challenges gate movement, not reach).
    """

    position_id: int
    adjacent_position_ids: list[int] = field(default_factory=list)


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
    blocks_flight: bool = False,
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
        blocks_flight=blocks_flight,
    )
    edge.full_clean()
    edge.save()
    return edge


def disconnect_positions(a: Position, b: Position) -> None:
    """Remove the edge between two positions (order-independent)."""
    lo, hi = (a, b) if a.pk < b.pk else (b, a)
    PositionEdge.objects.filter(position_a=lo, position_b=hi).delete()


# ---------------------------------------------------------------------------
# Blueprint authoring
# ---------------------------------------------------------------------------

_ERR_BLUEPRINT_CROSS = "Both positions of a blueprint edge must belong to the same blueprint."


def create_blueprint(name: str, *, description: str = "") -> PositionBlueprint:
    """Create and return a new PositionBlueprint."""
    return PositionBlueprint.objects.create(name=name, description=description)


def add_blueprint_position(
    blueprint: PositionBlueprint,
    name: str,
    *,
    kind: str = PositionKind.FEATURE,
    description: str = "",
) -> BlueprintPosition:
    """Create and return a new BlueprintPosition owned by blueprint."""
    return BlueprintPosition.objects.create(
        blueprint=blueprint, name=name, kind=kind, description=description
    )


def connect_blueprint_positions(
    a: BlueprintPosition,
    b: BlueprintPosition,
    *,
    is_passable: bool = True,
) -> BlueprintEdge:
    """Create a traversable edge between two blueprint positions, ordered canonically.

    The smaller-pk position becomes position_a (canonical ordering), mirroring
    ``connect_positions``. Raises PositionError if a and b belong to different
    blueprints. Calls full_clean() before save so self-loop / canonical-order
    constraints fire.
    """
    if a.blueprint_id != b.blueprint_id:
        raise PositionError(_ERR_BLUEPRINT_CROSS)
    if a.pk > b.pk:
        a, b = b, a
    edge = BlueprintEdge(
        blueprint=a.blueprint,
        position_a=a,
        position_b=b,
        is_passable=is_passable,
    )
    edge.full_clean()
    edge.save()
    return edge


def remove_blueprint(blueprint: PositionBlueprint) -> None:
    """Delete a blueprint (cascades positions and edges)."""
    blueprint.delete()


def instantiate_blueprint(
    blueprint: PositionBlueprint,
    room: ObjectDB,
    *,
    replace: bool = False,
) -> list[Position]:
    """Clone a blueprint's position graph into a room, returning the created Positions.

    Wraps the entire operation in a transaction so a mid-way failure rolls back cleanly.

    Args:
        blueprint: The PositionBlueprint to clone.
        room: The target room (ObjectDB) to stage.
        replace: If True, delete any existing positions in the room before staging.
                 Raises PositionError if any existing position has occupants.

    Returns:
        The list of newly-created Position instances.

    Raises:
        PositionError: If the room is already staged and replace=False, or if the
                       room has occupants when replace=True.
    """
    from django.db import transaction

    with transaction.atomic():
        already_staged = Position.objects.filter(room=room).exists()

        if already_staged and not replace:
            msg = "This room is already staged."
            raise PositionError(msg)

        if already_staged and replace:
            if ObjectPosition.objects.filter(position__room=room).exists():
                msg = "Cannot restage an occupied room."
                raise PositionError(msg)
            # Cascade deletes PositionEdges and ObjectPositions via FK on_delete=CASCADE.
            Position.objects.filter(room=room).delete()

        # Build Position instances from the blueprint without hitting the DB per-item.
        blueprint_positions = list(blueprint.positions.all())
        new_positions = [
            Position(
                room=room,
                name=bp_pos.name,
                kind=bp_pos.kind,
                description=bp_pos.description,
            )
            for bp_pos in blueprint_positions
        ]
        Position.objects.bulk_create(new_positions)

        # bulk_create may not populate PKs reliably on SQLite (pre-Django 3.0 behaviour).
        # Re-fetch the freshly created positions for this room and key by name.
        # This is safe because blueprint position names are unique per blueprint, so
        # within this room's newly-created set the name is unambiguous.
        live_map: dict[str, Position] = {
            pos.name: pos for pos in Position.objects.filter(room=room)
        }

        # Reproduce the blueprint's edges in the live graph.
        for edge in blueprint.edges.all():
            connect_positions(
                live_map[edge.position_a.name],
                live_map[edge.position_b.name],
                is_passable=edge.is_passable,
            )

        return list(live_map.values())


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def position_reachable(origin: Position, target: Position, reach: str) -> bool:
    """Whether `target` is reachable from `origin` under a TechniqueReach value.

    SAME     -> target is the same position.
    ADJACENT -> same position, or a directly-connected passable edge exists.
                (Gating challenges gate movement, not reach — an ADJACENT
                technique can strike across a movement-gated edge.)
    ANY      -> any position in the same room.
    """
    from world.magic.constants import TechniqueReach

    if reach == TechniqueReach.SAME:
        return origin.pk == target.pk
    if reach == TechniqueReach.ADJACENT:
        if origin.pk == target.pk:
            return True
        edge = edge_between(origin, target)
        return edge is not None and edge.is_passable
    if reach == TechniqueReach.ANY:
        return origin.room_id == target.room_id
    # Unknown reach value — conservative fallback.
    return False


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


def room_position_adjacency(room: ObjectDB) -> list[PositionAdjacency]:
    """Return the ADJACENT-reach adjacency map for every position in *room*.

    When called via ``EncounterDetailSerializer``, the upstream viewset's
    ``_base_queryset`` prefetches positions onto ``room.positions_cached`` and
    passable edges onto each position as ``passable_edges_as_a`` /
    ``passable_edges_as_b`` (all via ``Prefetch(to_attr=...)``).  This function
    detects those attrs and builds the map in-memory with zero extra queries.

    When the attrs are absent (e.g., unit-test direct calls), issues exactly
    two queries:
      1. All positions in the room (ordered by pk).
      2. All passable edges whose position_a is in this room (canonical order
         guarantees ``position_a.room == position_b.room`` per model constraint).

    Gating challenges are deliberately ignored — ADJACENT reach can strike
    across a movement-gated edge (matching ``position_reachable``'s ADJACENT
    branch in this module).

    Returns a ``PositionAdjacency`` per position in pk order; isolated
    positions (no edges) have an empty ``adjacent_position_ids`` list.
    """
    # Prefer prefetched data (zero queries); fall back to DB when absent.
    positions_cached = getattr(room, "positions_cached", None)  # noqa: GETATTR_LITERAL
    if positions_cached is not None:
        positions = sorted(positions_cached, key=lambda x: x.pk)
        return [
            PositionAdjacency(
                position_id=p.pk,
                # edges_as_a: p is position_a → neighbor is position_b_id
                # edges_as_b: p is position_b → neighbor is position_a_id
                adjacent_position_ids=sorted(
                    {edge.position_b_id for edge in getattr(p, "passable_edges_as_a", [])}  # noqa: GETATTR_LITERAL
                    | {edge.position_a_id for edge in getattr(p, "passable_edges_as_b", [])}  # noqa: GETATTR_LITERAL
                ),
            )
            for p in positions
        ]

    # Fallback path: 2 queries.
    positions = list(Position.objects.filter(room=room).order_by("pk"))
    position_ids = {p.pk for p in positions}

    # All passable edges in the room — canonical order means position_a.room
    # == room, so filtering on position_a__room covers both endpoints.
    edges = PositionEdge.objects.filter(
        position_a__room=room,
        is_passable=True,
    ).values_list("position_a_id", "position_b_id")

    # Build adjacency dict: position_id → sorted list of adjacent ids.
    adj: dict[int, list[int]] = {p.pk: [] for p in positions}
    for a_id, b_id in edges:
        if a_id in position_ids and b_id in position_ids:
            adj[a_id].append(b_id)
            adj[b_id].append(a_id)

    return [
        PositionAdjacency(position_id=p.pk, adjacent_position_ids=sorted(adj[p.pk]))
        for p in positions
    ]


def adjacent_open_positions(position: Position) -> list[PositionEdge]:
    """Return edges to adjacent passable, unblocked positions.

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
        for edge in adjacent_open_positions(current):
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


# ---------------------------------------------------------------------------
# Aerial layer (flight / airborne movement)
# ---------------------------------------------------------------------------


def _ground_positions(room: ObjectDB) -> list[Position]:
    """Return all non-AERIAL positions in the room."""
    return list(Position.objects.filter(room=room).exclude(kind=PositionKind.AERIAL))


def _aerial_property():
    """Return the 'aerial' Property (lazy import to avoid circular deps)."""
    from world.mechanics.models import Property

    return Property.objects.get(name=AERIAL_PROPERTY_NAME)


def materialize_aerial_layer(room: ObjectDB) -> None:
    """Build the AERIAL mirror over the room's ground positions (idempotent).

    Each ground position X gets an AERIAL twin "Above X" with elevation_anchor=X
    and a vertical edge X<->above-X. Horizontal aerial edges mirror ground
    adjacency (every PositionEdge between ground nodes) but are passable/ungated,
    so flight crosses over walls/chasms/gates.
    """
    if Position.objects.filter(room=room, kind=PositionKind.AERIAL).exists():
        return
    ground = _ground_positions(room)
    twin: dict[int, Position] = {}
    for g in ground:
        above = create_position(room, f"Above {g.name}", kind=PositionKind.AERIAL)
        above.elevation_anchor = g
        above.save(update_fields=["elevation_anchor"])
        twin[g.pk] = above
        connect_positions(g, above)  # vertical
    # Horizontal: mirror every ground edge (ignore passability/gating).
    # Edges with blocks_flight=True are NOT mirrored — no aerial passage exists.
    for edge in PositionEdge.objects.filter(position_a__room=room).exclude(
        position_a__kind=PositionKind.AERIAL
    ):
        if edge.blocks_flight:
            continue
        a, b = twin.get(edge.position_a_id), twin.get(edge.position_b_id)
        if a is not None and b is not None:
            connect_positions(a, b)


def teardown_aerial_layer(room: ObjectDB) -> None:
    """Delete every AERIAL position in the room (cascades aerial edges/occupancy)."""
    Position.objects.filter(room=room, kind=PositionKind.AERIAL).delete()


def enter_aerial(objectdb: ObjectDB) -> ObjectPosition:
    """Move objectdb to the AERIAL twin above its current position.

    Materializes the aerial layer if not yet present (idempotent).
    Sets the 'aerial' ObjectProperty on the object.

    Raises PositionError if the actor is unplaced (no ObjectPosition).
    Returns the existing ObjectPosition without moving if actor is already aerial.
    """
    from world.mechanics.models import ObjectProperty

    ground = position_of(objectdb)
    if ground is None:
        msg = "Cannot take flight: actor is not placed."
        raise PositionError(msg)
    if ground.kind == PositionKind.AERIAL:
        return objectdb.object_position
    room = objectdb.location
    materialize_aerial_layer(room)
    above = Position.objects.get(room=room, kind=PositionKind.AERIAL, elevation_anchor=ground)
    ObjectProperty.objects.update_or_create(
        object=objectdb,
        property=_aerial_property(),
        defaults={"value": 1},
    )
    return force_move_to_position(objectdb, above)


def leave_aerial(objectdb: ObjectDB) -> ObjectPosition:
    """Move objectdb back to its anchor ground position and clear the aerial property.

    Tears down the aerial layer once no AERIAL position in the room has occupants.
    Falls to the room's PRIMARY position if elevation_anchor is None.

    Raises PositionError if the actor is unplaced or is not in an aerial position.
    """
    from world.mechanics.models import ObjectProperty

    room = objectdb.location
    current = position_of(objectdb)
    if current is None:
        msg = "Cannot land: actor is not placed."
        raise PositionError(msg)
    if current.kind != PositionKind.AERIAL:
        msg = "Actor is not aerial."
        raise PositionError(msg)
    landing: Position | None = current.elevation_anchor
    if landing is None:
        landing = Position.objects.filter(room=room, kind=PositionKind.PRIMARY).first()
    if landing is None:
        msg = "No ground position to land on."
        raise PositionError(msg)
    obj_pos = force_move_to_position(objectdb, landing)
    ObjectProperty.objects.filter(object=objectdb, property=_aerial_property()).delete()
    # Tear down once no AERIAL node retains occupants.
    if not ObjectPosition.objects.filter(
        position__room=room, position__kind=PositionKind.AERIAL
    ).exists():
        teardown_aerial_layer(room)
    return obj_pos


def maybe_emit_fall(objectdb: ObjectDB, position: Position) -> bool:
    """Emit FELL if *position* is a CHASM. Returns whether an event was emitted.

    Idempotently installs the room-owned FELL → plummet trigger
    (``install_fall_triggers``) before emitting, so the reactive plummet consumer
    (``world.areas.positioning.plummet.begin_plummet``) is always present at the
    fall choke point (#1228).
    """
    if position.kind != PositionKind.CHASM:
        return False
    from flows.constants import EventName
    from flows.emit import emit_event
    from flows.events.payloads import FallEvent
    from world.areas.positioning.plummet import install_fall_triggers

    # The fall choke point guarantees the consumer exists: idempotently install
    # the room-owned FELL → plummet trigger right before emitting. No-ops when
    # the seeded TriggerDefinition is absent (content not wired here).
    install_fall_triggers(objectdb.location)
    emit_event(
        EventName.FELL,
        FallEvent(faller=objectdb, position=position),
        location=objectdb.location,
    )
    return True

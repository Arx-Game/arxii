"""Authoring, query, and movement services for the positioning system.

Positions + edges are room-anchored. A walker crosses an edge unless
``edge_blocks_crossing`` says no: an active gating challenge or a hard seal. A
resolved gate opens a sealed wall (#4606). How other movers cross is
``edge_crossing_cost`` by ``CreatureTraversal``, and ``find_path`` routes over it;
``strike_reaches`` is the reach rule for a strike's delivery (#4607). Every
position write goes through ``_commit_position``. A roofed position and a screened
position are cover facts the reach rules and the route search read directly (#4608).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import heapq
from itertools import pairwise
from typing import TYPE_CHECKING

from django.db.models import Q

from world.areas.positioning.constants import (
    AERIAL_PROPERTY_NAME,
    CreatureTraversal,
    PositionKind,
    RampartSignature,
)
from world.areas.positioning.exceptions import PositionError, PositionTransitionError
from world.areas.positioning.models import (
    BlueprintEdge,
    BlueprintPosition,
    ObjectPosition,
    Position,
    PositionBlueprint,
    PositionEdge,
    PositionShelter,
    Rampart,
    RampartElementProfile,
    invalidate_position_graph_caches,
)
from world.mechanics.models import ChallengeInstance

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import DamageType
    from world.mechanics.models import ChallengeTemplate


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


def set_position_cover(position: Position, *, roofed: bool, screens_ranged: bool) -> Position:
    """Mark ``position`` roofed and/or screened (#4608) and drop the room's cached graph.

    The reach rules and the route search read the flags off the position itself, so
    the aerial layer is left as it is: a roof closes the vertical edge without any
    change to that edge's row.
    """
    position.is_roofed = roofed
    position.screens_ranged = screens_ranged
    position.save(update_fields=["is_roofed", "screens_ranged"])
    invalidate_position_graph_caches(position.room)
    return position


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
    # QuerySet.delete() bypasses PositionEdge.delete()'s targeted cache pops.
    PositionEdge.objects.filter(position_a=lo, position_b=hi).delete()
    invalidate_position_graph_caches(lo.room)


# ---------------------------------------------------------------------------
# Conjured obstacles (#2019)
# ---------------------------------------------------------------------------


def create_conjured_obstacle(  # noqa: PLR0913
    position_a: Position,
    position_b: Position,
    *,
    caster_sheet: CharacterSheet | None,
    integrity: int | None,
    source_rampart: Rampart | None = None,
    duration_rounds: int | None = None,
    gating_challenge: ChallengeInstance | None = None,
    blocks_flight: bool = False,
) -> PositionEdge:
    """Seal the edge between two positions as a conjured obstacle.

    Uses update_or_create: if an edge already exists (staff-authored passable
    edge), updates it to impassable + sets duration/owner. At expiry/teardown,
    the edge is restored to passable (preserving the base edge).

    Last-writer-wins for concurrent barricades on the same edge: the later spell
    takes the row, including its integrity and Rampart link (#4606), so a Rampart
    collapse never opens an edge a later Barricade took over. A gating challenge
    the overwrite displaces is released (deactivated once nothing gates on it).

    ``integrity`` is the wall's strength. A Rampart's seal passes ``source_rampart``
    instead and stores no integrity of its own (the Rampart holds it); every other
    conjured wall passes an integer.
    """
    if (source_rampart is None) == (integrity is None):
        msg = "A conjured wall takes an integrity, or a Rampart that holds it, not both."
        raise ValueError(msg)
    if integrity is not None and integrity < 1:
        msg = "A conjured wall's integrity must be at least 1."
        raise ValueError(msg)
    if position_a.pk > position_b.pk:
        position_a, position_b = position_b, position_a
    previous = (
        PositionEdge.objects.filter(position_a=position_a, position_b=position_b)
        .select_related("gating_challenge")
        .first()
    )
    # Only a conjured wall's own gate is released; a staff-authored gate the spell
    # covers (a chasm's crossing) may be a room challenge in its own right.
    displaced_gate = (
        previous.gating_challenge if previous is not None and _is_conjured(previous) else None
    )
    wall_integrity = integrity
    edge, _created = PositionEdge.objects.update_or_create(
        position_a=position_a,
        position_b=position_b,
        defaults={
            "is_passable": False,
            "duration_rounds": duration_rounds,
            "created_by_sheet": caster_sheet,
            "gating_challenge": gating_challenge,
            "blocks_flight": blocks_flight,
            "integrity": wall_integrity,
            "max_integrity": wall_integrity,
            "source_rampart": source_rampart,
        },
    )
    if displaced_gate is not None and displaced_gate != gating_challenge:
        _release_gate(displaced_gate)
    return edge


def _is_conjured(edge: PositionEdge) -> bool:
    """Whether ``edge`` currently holds a conjured wall (a caster, a duration, a
    strength or a Rampart link), as opposed to its staff-authored state."""
    return (
        edge.created_by_sheet_id is not None
        or edge.duration_rounds is not None
        or edge.integrity is not None
        or edge.source_rampart_id is not None
    )


def edge_blocks_crossing(edge: PositionEdge) -> bool:
    """The walker rule (#4606): whether a mover on foot is stopped by ``edge``.

    Reads only the edge row. An active gating challenge blocks. A sealed edge with
    no gating challenge is a hard seal and blocks. A sealed edge whose challenge is
    no longer active is open: a resolved climb or breach leaves ``is_passable=False``
    on the row, and nothing flips it back. A deleted challenge (``SET_NULL``) reads
    as a hard seal, so the wall fails closed; it still falls through integrity,
    duration or a Rampart collapse. Reach (``position_reachable``) ignores gates.
    """
    if edge.gating_challenge_id is not None:
        return edge.gating_challenge.is_active
    return not edge.is_passable


def _release_gate(challenge: ChallengeInstance) -> None:
    """Deactivate a wall's gating challenge once no edge gates on it any more.

    One Rampart's sealed edges share a single challenge, so it stays live while any
    of them still points at it. Never a delete: a deleted challenge would turn the
    edges still pointing at it into hard seals. Saved through the instance so the
    identity-mapped row sees the change.
    """
    if not challenge.is_active:
        return
    if PositionEdge.objects.filter(gating_challenge=challenge).exists():
        return
    challenge.is_active = False
    challenge.save(update_fields=["is_active"])


def restore_edge(edge: PositionEdge) -> None:
    """Open a conjured wall again: the one restore for every way a wall ends (#4606).

    Sets the edge passable and clears its duration, caster, integrity, Rampart link
    and gating challenge. The challenge is deactivated (never deleted) once no other
    edge still gates on it, so a climb no longer shows for a wall that is gone.
    """
    gate = edge.gating_challenge
    edge.is_passable = True
    edge.duration_rounds = None
    edge.created_by_sheet = None
    edge.integrity = None
    edge.max_integrity = None
    edge.source_rampart = None
    edge.gating_challenge = None
    edge.save(
        update_fields=[
            "is_passable",
            "duration_rounds",
            "created_by_sheet",
            "integrity",
            "max_integrity",
            "source_rampart",
            "gating_challenge",
        ]
    )
    if gate is not None:
        _release_gate(gate)


def damage_barrier(edge: PositionEdge, chip: int, *, damage_type: DamageType | None = None) -> bool:
    """Chip the wall on ``edge`` by ``chip``. Returns True when the wall fell.

    The one mutation seam for wall integrity (#4606). A Rampart's seal routes to
    ``damage_rampart`` through the element resist the interception path uses (a
    melee, single-target strike: the element's resist row for ``damage_type``),
    floored at 1, so its collapse opens every edge it sealed. A plain conjured
    wall has no resist and loses integrity, and is restored at 0. An
    indestructible edge (no integrity) takes nothing. Integrity is shared, so
    several strikers in one round add up when each calls this once per chip.
    """
    if edge.source_rampart_id is not None:
        rampart = edge.source_rampart
        resisted = max(1, chip - rampart.element_profile.base_resist(damage_type))
        return damage_rampart(rampart, resisted)
    if edge.integrity is None:
        return False
    remaining = edge.integrity - chip
    if remaining <= 0:
        restore_edge(edge)
        return True
    edge.integrity = remaining
    edge.save(update_fields=["integrity"])
    return False


def teardown_conjured_obstacles(room: ObjectDB) -> None:
    """Restore all conjured obstacles in a room (scene end).

    Edges that pre-existed (had an edge before the obstacle was created) are
    restored to passable. Staff-authored edges (null created_by_sheet) are
    never touched.
    """
    conjured = PositionEdge.objects.filter(
        created_by_sheet__isnull=False,
        position_a__room=room,
    ).select_related("gating_challenge")
    for edge in conjured:
        restore_edge(edge)


def expire_obstacle_rounds(room: ObjectDB) -> None:
    """Decrement duration_rounds on conjured obstacles in the room.

    At 0, restore-to-passable (preserve the base edge). Staff-authored edges
    (null duration_rounds) are never decremented.
    """
    expiring = PositionEdge.objects.filter(
        duration_rounds__isnull=False,
        position_a__room=room,
    ).select_related("gating_challenge")
    for edge in expiring:
        edge.duration_rounds -= 1
        if edge.duration_rounds <= 0:
            restore_edge(edge)
        else:
            edge.save(update_fields=["duration_rounds"])


# ---------------------------------------------------------------------------
# Ramparts (#2209)
# ---------------------------------------------------------------------------


def raise_rampart(  # noqa: PLR0913
    position: Position,
    *,
    caster_sheet: CharacterSheet | None,
    element_profile: RampartElementProfile,
    integrity: int,
    duration_rounds: int | None = None,
    gating_challenge: ChallengeInstance | None = None,
) -> Rampart:
    """Raise a living barrier on position, replacing any existing one there.

    update_or_create keyed on position: re-casting on an already-warded position
    replaces it (last-writer-wins, mirrors create_conjured_obstacle) and resets
    max_integrity to the fresh cast's integrity. When element_profile's
    signature_behavior is SEAL_EDGES, also seals every PositionEdge touching this
    position via create_conjured_obstacle, sharing the same caster/duration/
    gating_challenge — Stone is a wall, not just a ward.
    """
    rampart, _created = Rampart.objects.update_or_create(
        position=position,
        defaults={
            "element_profile": element_profile,
            "integrity": integrity,
            "max_integrity": integrity,
            "created_by_sheet": caster_sheet,
            "duration_rounds": duration_rounds,
        },
    )
    if element_profile.signature_behavior != RampartSignature.SEAL_EDGES:
        # A recast on the same position keeps the row: a Stone Rampart recast as
        # Fire must not leave Stone's seals behind (#4606).
        unseal_rampart_edges(rampart)
    else:
        touching_edges = PositionEdge.objects.filter(
            Q(position_a=position) | Q(position_b=position)
        )
        for edge in touching_edges:
            create_conjured_obstacle(
                edge.position_a,
                edge.position_b,
                caster_sheet=caster_sheet,
                integrity=None,
                source_rampart=rampart,
                duration_rounds=duration_rounds,
                gating_challenge=gating_challenge,
            )
    return rampart


def rampart_at(position: Position) -> Rampart | None:
    """Return the Rampart raised on position, or None."""
    return Rampart.objects.filter(position=position).first()


def damage_rampart(rampart: Rampart, chip: int) -> bool:
    """Chip rampart.integrity down by chip. Returns True if it collapsed.

    The single mutation seam for rampart integrity — both clash-progress sync
    and combat interception funnel through here so the two never drift apart.
    Deletes the row at 0 (collapse); otherwise saves the reduced integrity.
    """
    new_integrity = rampart.integrity - chip
    if new_integrity <= 0:
        rampart.delete()  # Rampart.delete opens the edges it sealed (#4606)
        return True
    rampart.integrity = new_integrity
    rampart.save(update_fields=["integrity"])
    return False


def expire_rampart_rounds(room: ObjectDB) -> None:
    """Decrement duration_rounds on ramparts in the room; delete at 0.

    Staff-authored ramparts (null duration_rounds) are never decremented.
    Mirrors expire_obstacle_rounds.
    """
    expiring = Rampart.objects.filter(duration_rounds__isnull=False, position__room=room)
    for rampart in expiring:
        rampart.duration_rounds -= 1
        if rampart.duration_rounds <= 0:
            rampart.delete()  # opens the edges it sealed
        else:
            rampart.save(update_fields=["duration_rounds"])


def teardown_ramparts(room: ObjectDB) -> None:
    """Delete every Rampart in the room (scene end). Mirrors teardown_conjured_obstacles.

    Loops the rows rather than a queryset delete, which would skip
    ``Rampart.delete`` and so leave the edges it sealed shut.
    """
    for rampart in Rampart.objects.filter(position__room=room):
        rampart.delete()


def unseal_rampart_edges(rampart: Rampart) -> None:
    """Open every edge ``rampart`` sealed (#4606). ``Rampart.delete`` runs it first,
    and a recast with an element that does not seal runs it too.

    Only edges still linked to this Rampart: a later spell that overwrote an edge
    cleared the link and owns that wall now, so it stays sealed.
    """
    sealed = PositionEdge.objects.filter(source_rampart=rampart).select_related("gating_challenge")
    for edge in sealed:
        restore_edge(edge)


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
    gating_challenge_template: ChallengeTemplate | None = None,
) -> BlueprintEdge:
    """Create a traversable edge between two blueprint positions, ordered canonically.

    The smaller-pk position becomes position_a (canonical ordering), mirroring
    ``connect_positions``. Raises PositionError if a and b belong to different
    blueprints. Calls full_clean() before save so self-loop / canonical-order
    constraints fire. A non-null ``gating_challenge_template`` means
    ``instantiate_blueprint`` mints a live ``ChallengeInstance`` from it when this
    edge is cloned into a room.
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
        gating_challenge_template=gating_challenge_template,
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

    A blueprint edge with a ``gating_challenge_template`` mints a live
    ``ChallengeInstance`` when cloned. Restaging with ``replace=True`` deactivates
    (``is_active=False``) any such ``ChallengeInstance`` left behind by the room's
    prior staging — the cascade-delete below removes the old ``PositionEdge`` rows
    but does not touch the ``ChallengeInstance`` they pointed to.

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
            # Deactivate any gating ChallengeInstance the old edges pointed to — the
            # cascade-delete below removes the PositionEdge rows but does not touch
            # ChallengeInstance (the FK points the other way), which would otherwise
            # dangle as still-active with nothing referencing it.
            stale_challenge_ids = list(
                PositionEdge.objects.filter(
                    position_a__room=room, gating_challenge__isnull=False
                ).values_list("gating_challenge_id", flat=True)
            )
            if stale_challenge_ids:
                ChallengeInstance.objects.filter(pk__in=stale_challenge_ids).update_with_reason(
                    reason="issue #3817: intentional atomic write",
                    is_active=False,
                )
                # Bulk .update() writes the DB row directly, bypassing per-instance
                # .save() — the idmapper identity map never sees it, so any cached
                # ChallengeInstance for these pks would still report is_active=True.
                ChallengeInstance.flush_instance_cache()
            # Cascade deletes PositionEdges and ObjectPositions via FK on_delete=CASCADE.
            # Bulk delete bypasses the per-instance cache pops; an edgeless
            # blueprint would otherwise leave the pre-restage graph cached.
            Position.objects.filter(room=room).delete()
            invalidate_position_graph_caches(room)

        # Build Position instances from the blueprint without hitting the DB per-item.
        blueprint_positions = list(blueprint.positions.all())
        new_positions = [
            Position(
                room=room,
                name=bp_pos.name,
                kind=bp_pos.kind,
                description=bp_pos.description,
                layout_x=bp_pos.layout_x,
                layout_y=bp_pos.layout_y,
                is_roofed=bp_pos.is_roofed,
                screens_ranged=bp_pos.screens_ranged,
            )
            for bp_pos in blueprint_positions
        ]
        Position.objects.bulk_create(new_positions)
        # bulk_create bypasses Position.save()'s cache pop (both replace and
        # additive paths need the room's cached graph dropped).
        invalidate_position_graph_caches(room)

        # bulk_create may not populate PKs reliably on SQLite (pre-Django 3.0 behaviour).
        # Re-fetch the freshly created positions for this room and key by name.
        # This is safe because blueprint position names are unique per blueprint, so
        # within this room's newly-created set the name is unambiguous.
        live_map: dict[str, Position] = {
            pos.name: pos for pos in Position.objects.filter(room=room)
        }

        # Reproduce the blueprint's edges in the live graph.
        from world.mechanics.challenge_resolution import instantiate_challenge

        for edge in blueprint.edges.all():
            gating_challenge = None
            if edge.gating_challenge_template_id is not None:
                gating_challenge = instantiate_challenge(
                    edge.gating_challenge_template,
                    location=room,
                    target_object=room,
                )
            connect_positions(
                live_map[edge.position_a.name],
                live_map[edge.position_b.name],
                is_passable=edge.is_passable,
                gating_challenge=gating_challenge,
            )

        # Clone shelter templates into live PositionShelter rows.
        for bp_pos in blueprint_positions:
            live_pos = live_map[bp_pos.name]
            shelter_rows = [
                PositionShelter(
                    position=live_pos,
                    damage_type=bp_shelter.damage_type,
                    value=bp_shelter.value,
                    applies_to_attacks=bp_shelter.applies_to_attacks,
                )
                for bp_shelter in bp_pos.shelters.all()
            ]
            if shelter_rows:
                PositionShelter.objects.bulk_create(shelter_rows)

        return list(live_map.values())


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _reachable_within_hops(origin: Position, max_hops: int) -> set[Position]:
    """Positions reachable from ``origin`` within ``max_hops`` passable edges.

    Hop-limited BFS following reach semantics: traverses edges where
    ``edge.is_passable`` is True, ignoring active gating challenges (mirrors
    ADJACENT — gating challenges gate movement, not reach). The starting
    position is not included in the result.
    """
    seen: set[int] = {origin.pk}
    frontier: deque[tuple[Position, int]] = deque([(origin, 0)])
    result: set[Position] = set()
    while frontier:
        current, depth = frontier.popleft()
        if depth >= max_hops:
            continue
        edges = PositionEdge.objects.filter(
            Q(position_a=current) | Q(position_b=current),
            is_passable=True,
        )
        for edge in edges:
            other = edge.position_b if edge.position_a_id == current.pk else edge.position_a
            if other.pk not in seen:
                seen.add(other.pk)
                result.add(other)
                frontier.append((other, depth + 1))
    return result


def roof_between(a: Position, b: Position) -> bool:
    """True when a roof stands between ``a`` and ``b`` (#4608).

    That is: exactly one of the two is AERIAL and the other, a ground position, is
    roofed. No strike crosses it, whatever its reach or delivery, even though the
    aerial twin and its ground twin share a passable vertical edge, and no mover flies
    straight through it (``find_path``, ``move_to_position``).
    """
    a_aerial = a.kind == PositionKind.AERIAL
    b_aerial = b.kind == PositionKind.AERIAL
    if a_aerial == b_aerial:
        return False
    ground = b if a_aerial else a
    return ground.is_roofed


def _within_a_step(origin: Position, target: Position) -> bool:
    """Same position, or joined by a passable edge (the ADJACENT rule, gates ignored)."""
    if origin.pk == target.pk:
        return True
    edge = edge_between(origin, target)
    return edge is not None and edge.is_passable


def screen_blocks(origin: Position, target: Position) -> bool:
    """True when ``target`` is screened and ``origin`` is neither it nor beside it (#4608).

    A screen breaks line of sight: a missile or room-wide (ANY reach) strike at a
    screened position has to come from the same position or an adjacent one.
    """
    return target.screens_ranged and not _within_a_step(origin, target)


def position_reachable(
    origin: Position,
    target: Position,
    reach: str,
    *,
    reach_hops: int | None = None,
) -> bool:
    """Whether ``target`` is reachable from ``origin`` under a TechniqueReach value.

    Two cover rules come first (#4608): a roof between the two (``roof_between``)
    stops every reach, and a screened target (``screen_blocks``) stops an ANY strike
    from further than a step away.

    SAME     -> target is the same position.
    ADJACENT -> same position, or a directly-connected passable edge exists.
                (Gating challenges gate movement, not reach — an ADJACENT
                technique can strike across a movement-gated edge.)
    REACH_N  -> same position, or target is within ``reach_hops`` passable edges
                via BFS. Follows reach semantics (is_passable only, ignores
                active gating challenges — same as ADJACENT).
    ANY      -> any position in the same room.
    """
    from world.magic.constants import TechniqueReach

    if roof_between(origin, target):
        return False
    if reach == TechniqueReach.SAME:
        return origin.pk == target.pk
    if reach in (TechniqueReach.ADJACENT, TechniqueReach.REACH_N):
        if origin.pk == target.pk:
            return True
        if reach == TechniqueReach.ADJACENT:
            edge = edge_between(origin, target)
            return edge is not None and edge.is_passable
        max_hops = reach_hops if reach_hops is not None else 1
        return target in _reachable_within_hops(origin, max_hops)
    if reach == TechniqueReach.ANY:
        return origin.room_id == target.room_id and not screen_blocks(origin, target)
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
    # room.positions_cached is the Prefetch/query shared interface (Tehom's
    # pattern): combat's encounter queryset pre-fills it (with the nested edge
    # attrs) via Prefetch(to_attr=...); otherwise the Room cached_property runs
    # the same shape lazily. No probing, no fallback branch.
    positions = sorted(room.positions_cached, key=lambda x: x.pk)
    return [
        PositionAdjacency(
            position_id=p.pk,
            # edges_as_a: p is position_a → neighbor is position_b_id
            # edges_as_b: p is position_b → neighbor is position_a_id
            adjacent_position_ids=sorted(
                {edge.position_b_id for edge in p.passable_edges_as_a}
                | {edge.position_a_id for edge in p.passable_edges_as_b}
            ),
        )
        for p in positions
    ]


@dataclass(frozen=True)
class PositionNode:
    """One node in the tactical-map graph (#2006) — kind, elevation, and layout.

    ``rampart_*`` fields (#2209) are populated from the position's covering
    ``Rampart`` (one-to-one) when present, else all four are ``None``.
    ``is_roofed``/``screens_ranged`` (#4608) are the position's cover facts.
    """

    id: int
    name: str
    kind: str
    elevation_anchor_id: int | None
    layout_x: int | None
    layout_y: int | None
    rampart_element: str | None
    rampart_integrity: int | None
    rampart_max_integrity: int | None
    rampart_crack_state: str | None
    is_roofed: bool = False
    screens_ranged: bool = False


@dataclass(frozen=True)
class PositionEdgeInfo:
    """One edge in the tactical-map graph (#2006) — obstacle/gate visibility.

    Unlike PositionAdjacency (the ADJACENT-reach graph), this carries every
    edge. ``is_passable`` is the walker rule (``edge_blocks_crossing``), and
    ``gating_challenge_name`` names only a gate that is still active (#4606).
    """

    position_a_id: int
    position_b_id: int
    is_passable: bool
    blocks_flight: bool
    gating_challenge_name: str | None
    integrity: int | None = None
    max_integrity: int | None = None


@dataclass(frozen=True)
class PositionGraph:
    """The full node+edge graph for one room's tactical map (#2006)."""

    nodes: list[PositionNode] = field(default_factory=list)
    edges: list[PositionEdgeInfo] = field(default_factory=list)


def _position_node(position: Position, rampart: Rampart | None) -> PositionNode:
    return PositionNode(
        id=position.pk,
        name=position.name,
        kind=position.kind,
        elevation_anchor_id=position.elevation_anchor_id,
        layout_x=position.layout_x,
        layout_y=position.layout_y,
        rampart_element=rampart.element_profile.name if rampart else None,
        rampart_integrity=rampart.integrity if rampart else None,
        rampart_max_integrity=rampart.max_integrity if rampart else None,
        rampart_crack_state=rampart.crack_state if rampart else None,
        is_roofed=position.is_roofed,
        screens_ranged=position.screens_ranged,
    )


def _position_edge_info(edge: PositionEdge) -> PositionEdgeInfo:
    # The map shows what a walker meets (#4606): a resolved gate is no longer named,
    # and a climbed wall reads as passable even though its row stays sealed.
    blocked = edge_blocks_crossing(edge)
    gate = edge.gating_challenge if edge.gating_challenge_id else None
    gating_name = gate.template.name if gate is not None and gate.is_active else None
    barrier = edge.barrier_integrity
    return PositionEdgeInfo(
        position_a_id=edge.position_a_id,
        position_b_id=edge.position_b_id,
        is_passable=not blocked,
        blocks_flight=edge.blocks_flight,
        gating_challenge_name=gating_name,
        integrity=barrier[0] if barrier else None,
        max_integrity=barrier[1] if barrier else None,
    )


def position_graph(room: ObjectDB) -> PositionGraph:
    """Return the full node+edge graph for *room* — the tactical map's data (#2006).

    Unlike ``room_position_adjacency`` (the ADJACENT-reach graph, which drops
    impassable edges and ignores gating), this returns every position and
    every edge, with is_passable/blocks_flight/gating_challenge_name intact,
    for obstacle/gate visibility.

    ``room.positions_cached`` (with each position's full edge set on
    ``all_edges_as_a``) is either pre-filled by a viewset's
    ``Prefetch(to_attr=...)`` or lazily built by the Room cached_property —
    one shared interface, same shape both ways. Ramparts (#2209) come from one
    bulk query keyed by position id.

    Because edges are stored canonically (position_a.pk < position_b.pk),
    collecting only each position's edges_as_a across the whole room's
    position set yields every edge exactly once — no dedup needed.
    """

    # room.positions_cached is the Prefetch/query shared interface (see
    # room_adjacency above). rampart_or_none reads the warm path's
    # select_related cache for free (the zero-query contract, #2006); cold
    # callers pay one bounded lookup per position in the room.
    positions = sorted(room.positions_cached, key=lambda p: p.pk)
    nodes = [_position_node(p, p.rampart_or_none) for p in positions]
    edges = [_position_edge_info(edge) for p in positions for edge in p.all_edges_as_a]
    return PositionGraph(nodes=nodes, edges=edges)


def adjacent_open_positions(position: Position) -> list[PositionEdge]:
    """Return the edges a walker can cross from ``position`` (``edge_blocks_crossing``).

    An active gating challenge or a hard seal blocks; an edge whose gating
    challenge is no longer active is open even when it is still marked sealed (a
    climbed wall, #4606). Fetches all touching edges in one query (no queries in
    loops).
    """
    edges = PositionEdge.objects.filter(
        Q(position_a=position) | Q(position_b=position)
    ).select_related("position_a", "position_b", "gating_challenge")
    return [edge for edge in edges if not edge_blocks_crossing(edge)]


def reachable_positions(objectdb: ObjectDB) -> set[Position]:
    """Return the set of positions reachable from objectdb's current position.

    Multi-hop BFS over the edges a walker can cross (``edge_blocks_crossing``):
    an active gating challenge or a hard seal is not crossed. The starting
    position is not included.
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
# Path service and reach rule (#4607, slice 2 of #4576)
# ---------------------------------------------------------------------------

# What a climber or leaper pays to cross a wall that has a way past it.
GATED_CROSSING_HOPS = 2
_CROSSERS_OF_GATES = (CreatureTraversal.CLIMBS, CreatureTraversal.LEAPS)


def _crossing_cost(
    edge: PositionEdge, *, touches_aerial: bool, roofed: bool, traversal: str
) -> int | None:
    """Hops to cross ``edge`` for ``traversal``; None means closed to that mover.

    The edge row decides everything except whether either end is AERIAL and whether
    a roof stands between the ends (``roof_between``), which the caller supplies
    (``find_path`` reads them off its loaded node set). A roof closes the vertical
    edge to everyone (#4608): a flier lands beside a roofed position and walks in.
    """
    if roofed:
        return None
    blocked = edge_blocks_crossing(edge)
    if touches_aerial:
        # Only a flier enters the aerial layer (vertical and aerial-horizontal edges).
        return 1 if traversal == CreatureTraversal.FLIES and not blocked else None
    if not blocked:
        return 1
    if traversal in _CROSSERS_OF_GATES and edge.gating_challenge_id is not None:
        # edge_blocks_crossing only blocks a gated edge while its challenge is active.
        return GATED_CROSSING_HOPS
    # A hard seal, or a walker or flier at any wall (a flier goes over by the aerial layer).
    return None


def edge_crossing_cost(edge: PositionEdge, traversal: str) -> int | None:
    """Hops a mover of ``traversal`` (a ``CreatureTraversal``) pays to cross ``edge``.

    None means the edge is closed to that mover. An edge touching an AERIAL position
    costs 1 for FLIES and is closed to every other traversal. A ground edge a walker
    can cross costs 1 for everyone. A wall with an active gating challenge costs
    CLIMBS and LEAPS ``GATED_CROSSING_HOPS`` and is closed to WALKS and FLIES; a hard
    seal is closed to all. The vertical edge between a roofed position and the air
    above it is closed to all (#4608).
    """
    a, b = edge.position_a, edge.position_b
    touches_aerial = PositionKind.AERIAL in (a.kind, b.kind)
    return _crossing_cost(
        edge, touches_aerial=touches_aerial, roofed=roof_between(a, b), traversal=traversal
    )


@dataclass(frozen=True)
class _RoomGraph:
    """One room's positions and edges, loaded once from ``room.positions_cached``."""

    nodes: dict[int, Position]
    edges: dict[tuple[int, int], PositionEdge]
    neighbours: dict[int, list[tuple[int, PositionEdge]]]

    def cost(self, edge: PositionEdge, traversal: str) -> int | None:
        a, b = self.nodes.get(edge.position_a_id), self.nodes.get(edge.position_b_id)
        touches_aerial = any(p is not None and p.kind == PositionKind.AERIAL for p in (a, b))
        roofed = a is not None and b is not None and roof_between(a, b)
        return _crossing_cost(
            edge, touches_aerial=touches_aerial, roofed=roofed, traversal=traversal
        )


def _room_graph(origin: Position) -> _RoomGraph:
    """Build the routing graph for ``origin``'s room from the database (two queries).

    Not from ``room.positions_cached``: in a running server the per-position edge
    caches a page load prefetched can outlive the aerial layer a flier's planning just
    built, and Django's prefetch never refills a cache that is already set, so a route
    search read from them missed the new vertical edges (#4607, found in a live run).
    Edges are canonical (position_a.pk < position_b.pk), so each is read once.
    """
    positions = list(Position.objects.filter(room_id=origin.room_id))
    nodes = {p.pk: p for p in positions}
    nodes.setdefault(origin.pk, origin)
    edges: dict[tuple[int, int], PositionEdge] = {}
    neighbours: dict[int, list[tuple[int, PositionEdge]]] = {pk: [] for pk in nodes}
    room_edges = PositionEdge.objects.filter(position_a__room_id=origin.room_id).select_related(
        "gating_challenge__template", "source_rampart"
    )
    for edge in room_edges:
        a_id, b_id = edge.position_a_id, edge.position_b_id
        if a_id not in nodes or b_id not in nodes:
            continue
        edges[(a_id, b_id)] = edge
        neighbours[a_id].append((b_id, edge))
        neighbours[b_id].append((a_id, edge))
    return _RoomGraph(nodes=nodes, edges=edges, neighbours=neighbours)


def is_breakable_barrier(edge: PositionEdge) -> bool:
    """Whether ``edge`` holds a wall that damage can bring down (#4609).

    A plain conjured wall with integrity, or a Rampart's seal (the Rampart holds the
    integrity). A staff-authored seal, which has neither, is indestructible.
    """
    return edge.integrity is not None or edge.source_rampart_id is not None


def barrier_integrity(edge: PositionEdge) -> int | None:
    """The live strength of the wall on ``edge``: its Rampart's integrity for a Rampart's
    seal, else the edge's own. None for an indestructible edge (#4609)."""
    if edge.source_rampart_id is not None:
        return edge.source_rampart.integrity
    return edge.integrity


def _hop_cost(
    graph: _RoomGraph, edge: PositionEdge, traversal: str, *, through_barriers: bool
) -> int | None:
    """``graph.cost``, except that ``through_barriers`` lets a ground mover cross a wall
    damage can bring down at 1 hop, as though it were already down."""
    hop = graph.cost(edge, traversal)
    if hop is not None or not through_barriers or not is_breakable_barrier(edge):
        return hop
    ends = (graph.nodes.get(edge.position_a_id), graph.nodes.get(edge.position_b_id))
    if any(end is None or end.kind == PositionKind.AERIAL for end in ends):
        return None
    return 1


def find_path(
    origin: Position,
    goal_test: Callable[[Position], bool],
    *,
    traversal: str,
    through_barriers: bool = False,
) -> list[Position] | None:
    """The cheapest route from ``origin`` to the first position ``goal_test`` accepts.

    Returns ``[origin, ..., goal]`` (``[origin]`` when the origin already passes), or
    None when no position the mover can reach passes. Cost is the summed
    ``edge_crossing_cost`` for ``traversal``; ties go to fewer steps, then to the
    lower position pk, so the answer is deterministic. Only a FLIES mover enters an
    AERIAL position, and only through the aerial layer already in the room (this
    never materializes it). Positions have no capacity: several movers may share one.
    The room graph is read once from ``room.positions_cached``.

    ``through_barriers`` (#4609) is the barrier-ignoring route an NPC weighs before it
    bashes: a ground wall that damage can bring down (``is_breakable_barrier``) counts
    as open at 1 hop. An indestructible seal stays closed.
    """
    graph = _room_graph(origin)
    best: dict[int, tuple[int, int]] = {origin.pk: (0, 0)}
    parent: dict[int, int] = {}
    frontier: list[tuple[int, int, int]] = [(0, 0, origin.pk)]
    done: set[int] = set()
    while frontier:
        cost, steps, pk = heapq.heappop(frontier)
        if pk in done:
            continue
        done.add(pk)
        if goal_test(graph.nodes[pk]):
            return _walk_back(graph, parent, pk)
        for other, edge in graph.neighbours[pk]:
            hop = _hop_cost(graph, edge, traversal, through_barriers=through_barriers)
            if hop is None or other in done:
                continue
            candidate = (cost + hop, steps + 1)
            if other not in best or candidate < best[other]:
                best[other] = candidate
                parent[other] = pk
                heapq.heappush(frontier, (*candidate, other))
    return None


def path_costs_from(origin: Position, *, traversal: str) -> dict[int, int]:
    """Hops from ``origin`` to every position a mover of ``traversal`` can reach, by pk.

    The same costs ``find_path`` routes over (``edge_crossing_cost``); the origin costs
    0, and a position the mover cannot reach is absent. Used to measure path distance
    (an NPC retreating from its enemies, #4609).
    """
    graph = _room_graph(origin)
    best: dict[int, int] = {origin.pk: 0}
    frontier: list[tuple[int, int]] = [(0, origin.pk)]
    done: set[int] = set()
    while frontier:
        cost, pk = heapq.heappop(frontier)
        if pk in done:
            continue
        done.add(pk)
        for other, edge in graph.neighbours[pk]:
            hop = graph.cost(edge, traversal)
            if hop is None or other in done:
                continue
            if other not in best or cost + hop < best[other]:
                best[other] = cost + hop
                heapq.heappush(frontier, (cost + hop, other))
    return best


def first_closed_edge(path: list[Position], *, traversal: str) -> PositionEdge | None:
    """The first edge along ``path`` closed to a mover of ``traversal``, or None.

    A barrier-ignoring route (``find_path(..., through_barriers=True)``) crosses the
    walls it found in the way; this names the first of them (#4609).
    """
    if len(path) <= 1:
        return None
    graph = _room_graph(path[0])
    for here, there in pairwise(path):
        edge = graph.edges.get(tuple(sorted((here.pk, there.pk))))
        if edge is None or graph.cost(edge, traversal) is None:
            return edge
    return None


def _walk_back(graph: _RoomGraph, parent: dict[int, int], goal_pk: int) -> list[Position]:
    chain = [goal_pk]
    while chain[-1] in parent:
        chain.append(parent[chain[-1]])
    return [graph.nodes[pk] for pk in reversed(chain)]


def step_costs(
    path: list[Position], *, traversal: str, through_barriers: bool = False
) -> list[int]:
    """The hop cost of each step of ``path`` for ``traversal`` (``len(path) - 1`` items).

    Lets a caller cut a ``find_path`` route to a hop budget. Raises PositionError
    when two consecutive positions share no edge, or the edge is closed to the mover.
    ``through_barriers`` prices a barrier-ignoring route as ``find_path`` does.
    """
    if len(path) <= 1:  # a path of one position takes no step
        return []
    graph = _room_graph(path[0])
    costs: list[int] = []
    for here, there in pairwise(path):
        lo, hi = sorted((here.pk, there.pk))
        edge = graph.edges.get((lo, hi))
        hop = (
            _hop_cost(graph, edge, traversal, through_barriers=through_barriers)
            if edge is not None
            else None
        )
        if hop is None:
            msg = f"No crossing from {here.name} to {there.name} for {traversal}."
            raise PositionError(msg)
        costs.append(hop)
    return costs


def strike_reaches(
    attacker_pos: Position | None,
    target_pos: Position | None,
    delivery: str,
) -> bool:
    """Whether a strike of ``delivery`` (a ``StrikeDelivery``) lands from one position on another.

    MELEE needs the same or an adjacent position (``position_reachable``'s ADJACENT rule:
    a passable edge, gates ignored); MISSILE reaches anywhere in the room (ANY). An
    unknown delivery is treated as MELEE. Either position missing is reachable (an
    unplaced combatant stays lenient). The cover rules come first, as in
    ``position_reachable`` (#4608): a roof between the two stops every delivery, and a
    MISSILE at a screened target must come from the same or an adjacent position.
    """
    from world.combat.constants import StrikeDelivery

    if attacker_pos is None or target_pos is None:
        return True
    if roof_between(attacker_pos, target_pos):
        return False
    if delivery == StrikeDelivery.MISSILE:
        return attacker_pos.room_id == target_pos.room_id and not screen_blocks(
            attacker_pos, target_pos
        )
    if attacker_pos.pk == target_pos.pk:
        return True
    edge = _room_graph(attacker_pos).edges.get(tuple(sorted((attacker_pos.pk, target_pos.pk))))
    return edge is not None and edge.is_passable


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
_ERR_MOVE_CANNOT_FLY = "You cannot fly."
_ERR_MOVE_ROOFED = "A roof is in the way."
_ERR_TAKE_ALREADY_PLACED = "You are already placed somewhere — move instead."
_ERR_TAKE_NOT_ENTRY = "You cannot enter the position graph there."


def place_in_position(objectdb: ObjectDB, position: Position) -> ObjectPosition:
    """Place objectdb in position (setup / staff teleport).

    Raises PositionError if position.room != objectdb.location.
    Uses update_or_create so calling twice is idempotent (updates occupancy).
    """
    if position.room_id != objectdb.db_location_id:
        raise PositionError(_ERR_PLACE_CROSS_ROOM)
    return _commit_position(objectdb, position)


def _commit_position(objectdb: ObjectDB, position: Position) -> ObjectPosition:
    """The one writer of an object's position (#4607).

    Writes the ``ObjectPosition`` row, drops the cached ``current_position`` of every
    combat opponent and participant this object is (the rows are identity-mapped, so
    a stale cache would outlive the move), then re-reconciles sunlight.
    """
    from world.combat.models import CombatOpponent, CombatParticipant

    obj_pos, _ = ObjectPosition.objects.update_or_create(
        objectdb=objectdb,
        defaults={"position": position},
    )
    # Only identity-mapped rows can hold the cached property, so walk the map (no query).
    # CharacterSheet shares ObjectDB's pk, so a participant's sheet id is the object's pk.
    for opponent in CombatOpponent.get_all_cached_instances():
        if opponent.objectdb_id == objectdb.pk:
            opponent.__dict__.pop("current_position", None)
    for participant in CombatParticipant.get_all_cached_instances():
        if participant.character_sheet_id == objectdb.pk:
            participant.__dict__.pop("current_position", None)
    _reconcile_sun_after_position_change(objectdb)
    return obj_pos


def _reconcile_sun_after_position_change(objectdb: ObjectDB) -> None:
    """Position changed: re-reconcile sunlight exposure (#2846) — stepping under the
    tent should register immediately. No-op for non-characters and never raises
    (isolation lives in the shared safe wrapper)."""
    from world.species.services import reconcile_sun_exposure_safely

    reconcile_sun_exposure_safely(objectdb)


_ENTRY_KINDS = (PositionKind.PRIMARY, PositionKind.FEATURE)


def take_position(objectdb: ObjectDB, position: Position) -> ObjectPosition:
    """Voluntary entry onto the position graph for an UNPLACED actor (#2005).

    Restricted to ground entry-point kinds so voluntary entry can't bypass
    gating challenges, blocks_flight, or chasm/fall semantics (spec Decision 1);
    ELEVATED/AERIAL/etc. are reached through move_to_position / enter_aerial.
    place_in_position stays the unchecked staff/system primitive.
    """
    if position.room_id != objectdb.db_location_id:
        raise PositionError(_ERR_PLACE_CROSS_ROOM)
    if position_of(objectdb) is not None:
        raise PositionError(_ERR_TAKE_ALREADY_PLACED)
    if position.kind not in _ENTRY_KINDS:
        raise PositionError(_ERR_TAKE_NOT_ENTRY)
    if not _can_move(objectdb):
        raise PositionTransitionError(_ERR_MOVE_IMMOBILE)
    return place_in_position(objectdb, position)


def move_to_position(objectdb: ObjectDB, target: Position) -> ObjectPosition:
    """Voluntary move from current position to target position.

    Validation order (each failure raises PositionTransitionError):
    1. target is in the same room as objectdb
    2. objectdb is currently placed in a position
    3. an edge exists between current and target
    4. the edge does not block a walker (``edge_blocks_crossing``): an active
       gating challenge names itself; a hard seal is "The way is blocked."
    5. an AERIAL target needs the mover to hold the ``aerial`` property: "You cannot fly."
    6. no roof stands between the two (``roof_between``): "A roof is in the way." (#4608)
    7. the actor's MOVEMENT capability > 0 (characters only)
    """
    if target.room_id != objectdb.db_location_id:
        raise PositionTransitionError(_ERR_MOVE_CROSS_ROOM)

    current = position_of(objectdb)
    if current is None:
        raise PositionTransitionError(_ERR_MOVE_UNPLACED)

    edge = edge_between(current, target)
    if edge is None:
        raise PositionTransitionError(_ERR_MOVE_NO_PATH)

    if edge_blocks_crossing(edge):
        if edge.gating_challenge_id is not None:
            challenge_name = edge.gating_challenge.template.name
            msg = f"Crossing that requires getting past {challenge_name}."
            raise PositionTransitionError(msg)
        raise PositionTransitionError(_ERR_MOVE_BLOCKED)

    if target.kind == PositionKind.AERIAL and not is_aerial(objectdb):
        raise PositionTransitionError(_ERR_MOVE_CANNOT_FLY)

    if roof_between(current, target):
        raise PositionTransitionError(_ERR_MOVE_ROOFED)

    if not _can_move(objectdb):
        raise PositionTransitionError(_ERR_MOVE_IMMOBILE)

    return _commit_position(objectdb, target)


def is_aerial(objectdb: ObjectDB) -> bool:
    """Whether objectdb holds the ``aerial`` property (it has taken flight).

    Only an airborne mover may step onto an AERIAL position (``move_to_position``), so
    the move list offers those positions to it alone.
    """
    from world.mechanics.models import ObjectProperty

    return ObjectProperty.objects.filter(
        object=objectdb, property__name=AERIAL_PROPERTY_NAME
    ).exists()


def force_move_to_position(objectdb: ObjectDB, target: Position) -> ObjectPosition:
    """Move objectdb to target, bypassing capability + gate checks.

    Only requires same room. No edge required.
    """
    if target.room_id != objectdb.db_location_id:
        raise PositionError(_ERR_PLACE_CROSS_ROOM)
    return _commit_position(objectdb, target)


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
    # A page load may have prefetched the ground positions' edge lists; drop them all so
    # the tactical map and every later reader see the new vertical edges (#4607).
    invalidate_position_graph_caches(room)


@contextmanager
def aerial_layer_for_route(room: ObjectDB) -> Iterator[None]:
    """Hold the room's aerial layer up while a flier searches and walks a route (#4607).

    ``find_path`` only routes a flier through a layer that exists, so this builds one
    when the room has none, and takes it down again on the way out unless someone ended
    up airborne. A route search alone therefore never leaves "Above" positions on the
    map. A layer that already existed is left as it was.
    """
    existed = Position.objects.filter(room=room, kind=PositionKind.AERIAL).exists()
    if not existed:
        materialize_aerial_layer(room)
    try:
        yield
    finally:
        airborne = ObjectPosition.objects.filter(
            position__room=room, position__kind=PositionKind.AERIAL
        ).exists()
        if not existed and not airborne:
            teardown_aerial_layer(room)


def teardown_aerial_layer(room: ObjectDB) -> None:
    """Delete every AERIAL position in the room (cascades aerial edges/occupancy)."""
    # QuerySet.delete() bypasses the per-instance cache pops; surviving ground
    # positions would otherwise keep serving edges to the deleted aerial twins.
    Position.objects.filter(room=room, kind=PositionKind.AERIAL).delete()
    invalidate_position_graph_caches(room)


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


# ---------------------------------------------------------------------------
# Position shelter
# ---------------------------------------------------------------------------


def position_shelter_value(
    position: Position, damage_type: DamageType, *, attacks_only: bool = False
) -> int:
    """Sum of all PositionShelter.current_value() for (position, damage_type).

    Returns 0 if no shelter rows exist. Multiple rows stack additively.

    Args:
        attacks_only: When True, only sum rows with applies_to_attacks=True
            (attack-cover). When False (default), sum ALL rows (hazard + attack).
    """
    qs = position.shelters.filter(damage_type=damage_type)
    if attacks_only:
        qs = qs.filter(applies_to_attacks=True)
    return sum(ps.current_value() for ps in qs)


def cleanup_position_shelters(*, now: datetime | None = None) -> int:
    """Delete PositionShelter rows whose current_value() has decayed to zero.

    Iterates rows with non-zero ``change_per_day`` (zero-rate rows never
    decay), computes ``current_value()`` in Python, and deletes those whose
    value has crossed zero. Returns the count of rows deleted.

    Mirrors ``world.locations.services.cleanup_decayed_modifiers``.
    """
    from django.db import transaction

    with transaction.atomic():
        candidates = PositionShelter.objects.exclude(change_per_day=0).select_for_update()
        to_delete_ids: list[int] = [row.pk for row in candidates if row.current_value(now=now) == 0]
        if to_delete_ids:
            PositionShelter.objects.filter(pk__in=to_delete_ids).delete()
        return len(to_delete_ids)

"""Room-to-room travel pathfinding (#2163) — the room-level sibling of this
package's intra-room `position_graph`/`reachable_positions` (services.py).

Frontier-batched BFS: each level fetches every outbound exit for the entire
current frontier in one query (mirroring `world.areas.services.area_subtree_pks`'s
`parent_id__in=[...]` batching over the Area tree), never one room at a time.
This is the fix for the exact failure mode that broke naive per-room BFS at
scale in a prior project — the per-room query cost itself is cheap (Evennia's
`.exits`/`.contents` is a single cached query per room instance), but an
unbounded frontier fan-out without batching still costs one query per room
visited. Batching collapses that to one query per BFS *level*.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from evennia.objects.models import ObjectDB

from evennia_extensions.models import room_is_publicly_listed


def _area_id(room: ObjectDB) -> int | None:
    """The room's Area pk, or None if it has no RoomProfile / no Area set."""
    try:
        return room.room_profile.area_id
    except ObjectDoesNotExist:
        return None


def _is_usable_waypoint(dest: ObjectDB, visited: set[int], area_id: int | None) -> bool:
    """Whether `dest` is a not-yet-visited, publicly-listed room in the target Area.

    Shared gate for both intermediate waypoints and the destination room itself —
    keeping this a single predicate is what pulls find_route's per-exit branching
    under the complexity threshold without changing any of the batching logic.
    """
    if dest is None or dest.id in visited:
        return False
    if not room_is_publicly_listed(dest):
        return False
    return _area_id(dest) == area_id


def find_route(origin_room: ObjectDB, destination_room: ObjectDB) -> list[ObjectDB] | None:
    """Find a public-room-only walking route from origin to destination.

    Scoped to same-Area travel only (#2163 Decision 6) — cross-Area routing
    needs Area-to-Area connectivity data this codebase doesn't have yet.

    Returns an ordered list of Exit ObjectDB instances forming the route, or
    None if unreachable, the destination isn't publicly listed, the rooms are
    in different Areas, or the route would exceed TRAVEL_MAX_HOPS.
    """
    if origin_room.id == destination_room.id:
        return []

    origin_area_id = _area_id(origin_room)
    dest_area_id = _area_id(destination_room)
    if origin_area_id is None or origin_area_id != dest_area_id:
        return None

    if not room_is_publicly_listed(destination_room):
        return None

    max_hops = settings.TRAVEL_MAX_HOPS

    # predecessor[room_id] = (exit_objectdb, previous_room_id)
    predecessor: dict[int, tuple[ObjectDB, int]] = {}
    visited: set[int] = {origin_room.id}
    frontier: set[int] = {origin_room.id}

    for _hop in range(max_hops):
        if not frontier:
            return None

        # One bulk query for the entire frontier's outbound exits — the
        # load-bearing batching step (#2163 Decision 7). select_related
        # walks both the destination room AND its RoomProfile (a reverse
        # OneToOne, select_related-able) in the SAME query — without the
        # room_profile leg, every room_is_publicly_listed()/_area_id() call
        # below would issue its own query per candidate room, silently
        # reintroducing the exact per-room N+1 this function exists to avoid.
        exits = list(
            ObjectDB.objects.filter(
                db_location_id__in=frontier,
                db_destination__isnull=False,
            ).select_related("db_destination__room_profile")
        )

        next_frontier: set[int] = set()
        for exit_obj in exits:
            dest = exit_obj.db_destination
            if not _is_usable_waypoint(dest, visited, origin_area_id):
                continue

            predecessor[dest.id] = (exit_obj, exit_obj.db_location_id)
            visited.add(dest.id)

            if dest.id == destination_room.id:
                return _reconstruct_path(predecessor, origin_room.id, destination_room.id)

            next_frontier.add(dest.id)

        frontier = next_frontier

    return None


def _reconstruct_path(
    predecessor: dict[int, tuple[ObjectDB, int]],
    origin_id: int,
    destination_id: int,
) -> list[ObjectDB]:
    """Walk the predecessor chain backward from destination to origin, then reverse."""
    path: list[ObjectDB] = []
    current_id = destination_id
    while current_id != origin_id:
        exit_obj, prev_id = predecessor[current_id]
        path.append(exit_obj)
        current_id = prev_id
    path.reverse()
    return path

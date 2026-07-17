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
from evennia.objects.models import ObjectDB

from evennia_extensions.models import room_is_publicly_listed


def _is_usable_waypoint(dest: ObjectDB, visited: set[int]) -> bool:
    """Whether `dest` is a not-yet-visited, publicly-listed room.

    Shared gate for both intermediate waypoints and the destination room itself —
    keeping this a single predicate is what pulls find_route's per-exit branching
    under the complexity threshold without changing any of the batching logic.

    No Area check here (#2223 Decision 1): the exit graph itself IS the
    connectivity. A room-level Exit that crosses an Area boundary is exactly as
    usable a hop as one that stays within a single Area — there's no separate
    Area-to-Area adjacency model to consult, and none is needed, since BFS
    already walks whatever exits actually exist.
    """
    if dest is None or dest.id in visited:
        return False
    return room_is_publicly_listed(dest)


def find_route(origin_room: ObjectDB, destination_room: ObjectDB) -> list[ObjectDB] | None:
    """Find a public-room-only walking route from origin to destination.

    Walks the room/exit graph directly with no regard to Area boundaries
    (#2223 Decision 1): a chain of exits that physically connects origin to
    destination produces a route whatever Areas it crosses along the way. The
    exit graph IS the connectivity data — a separate Area-to-Area adjacency
    model would only duplicate what exits already encode, need hand
    maintenance, and still couldn't produce a walkable route by itself (you'd
    walk the exit graph anyway). #2163's original same-Area routing is simply
    the special case where every room on the path happens to share one Area.

    Returns an ordered list of Exit ObjectDB instances forming the route, or
    None if unreachable, the destination isn't publicly listed, or the route
    would exceed TRAVEL_MAX_HOPS.
    """
    if origin_room.id == destination_room.id:
        return []

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
        # room_profile leg, every room_is_publicly_listed() call below would
        # issue its own query per candidate room, silently reintroducing the
        # exact per-room N+1 this function exists to avoid.
        exits = list(
            ObjectDB.objects.filter(
                db_location_id__in=frontier,
                db_destination__isnull=False,
            ).select_related("db_destination__room_profile__area")
        )

        next_frontier: set[int] = set()
        for exit_obj in exits:
            dest = exit_obj.db_destination
            if not _is_usable_waypoint(dest, visited):
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

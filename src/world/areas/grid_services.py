"""Area-generic room-graph core (#2449).

Extracted from ``world.buildings.room_services`` (#670): rooms, symmetric exit
pairs, grid-cell placement, and BFS reachability, with no notion of budgets,
ownership, or ``Building`` — those stay in ``room_services``, which delegates
the mechanical room/exit/grid operations here. This is the shared substrate
for both the owner-facing building room-builder and the staff world-builder
canvas (epic #2436).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia_extensions.models import RoomProfile, RoomSizeTier
from world.areas.constants import GridOrigin

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB
    from evennia.objects.objects import DefaultObject

    from world.areas.models import Area


class GridServiceError(Exception):
    """A grid-service operation was refused; carries ``user_message``.

    Never surface ``str(exc)`` to API responses — use ``exc.user_message``.
    """

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def _set_room_description(room: DefaultObject, description: str) -> None:
    from evennia_extensions.models import ObjectDisplayData  # noqa: PLC0415

    display, _ = ObjectDisplayData.objects.get_or_create(object=room)
    display.permanent_description = description
    display.save()


def create_room(  # noqa: PLR0913 — mirrors dig_room's full room-creation surface
    *,
    area: Area,
    name: str,
    description: str = "",
    size: RoomSizeTier | None = None,
    grid_x: int | None = None,
    grid_y: int | None = None,
    floor: int = 0,
    origin: str = GridOrigin.PLAYER,
    fixture_key: str | None = None,
) -> RoomProfile:
    """Create a room object + its RoomProfile, with a written display description.

    Cosmetic grid placement (``grid_x``/``grid_y``/``floor``) and authorship
    (``origin``/``fixture_key``) are the caller's responsibility to validate —
    this is a pure creation primitive with no budget or ownership checks.
    """
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    room = evennia_create.create_object(
        typeclass="typeclasses.rooms.Room",
        key=name.strip(),
        nohome=True,
    )
    profile, _ = RoomProfile.objects.update_or_create(
        objectdb=room,
        defaults={
            "area": area,
            "is_outdoor": False,
            "size": size,
            "grid_x": grid_x,
            "grid_y": grid_y,
            "floor": floor,
            "origin": origin,
            "fixture_key": fixture_key,
        },
    )
    _set_room_description(room, description)
    return profile


def _create_exit(
    *, name: str, aliases: tuple[str, ...], source: DefaultObject, destination: DefaultObject
) -> ObjectDB:
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    exit_obj = evennia_create.create_object(
        typeclass="typeclasses.exits.Exit",
        key=name,
        location=source,
        destination=destination,
        nohome=True,
    )
    for alias in aliases:
        exit_obj.aliases.add(alias)
    return exit_obj


def create_exit_pair(  # noqa: PLR0913 — a symmetric pair needs both directions' name+aliases
    *,
    name: str,
    aliases: tuple[str, ...],
    reverse_name: str,
    reverse_aliases: tuple[str, ...],
    room_a: DefaultObject,
    room_b: DefaultObject,
) -> tuple[ObjectDB, ObjectDB]:
    """Create a symmetric exit pair between two existing rooms (any areas).

    No same-area requirement — cross-area exits (portals, travel links) are
    valid; that constraint belongs to callers like ``room_services.link_rooms``
    that must keep a building's interior self-contained.
    """
    forward = _create_exit(name=name, aliases=aliases, source=room_a, destination=room_b)
    backward = _create_exit(
        name=reverse_name, aliases=reverse_aliases, source=room_b, destination=room_a
    )
    return forward, backward


def cell_occupied(area: Area, x: int, y: int, floor: int) -> bool:
    """Whether a room already sits at this grid cell within ``area``."""
    return RoomProfile.objects.filter(area=area, grid_x=x, grid_y=y, floor=floor).exists()


def exits_for_rooms(room_ids: set[int]) -> QuerySet:
    """Exits whose location AND destination are both in ``room_ids``."""
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    return ObjectDB.objects.filter(
        db_typeclass_path="typeclasses.exits.Exit",
        db_location_id__in=room_ids,
        db_destination_id__in=room_ids,
    )


def exits_from_rooms(room_ids: set[int]) -> QuerySet:
    """Exits whose location is in ``room_ids`` (destination may lie outside it).

    Needed for builder payloads that show cross-area destinations at the edge
    of the rooms currently in view.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    return ObjectDB.objects.filter(
        db_typeclass_path="typeclasses.exits.Exit",
        db_location_id__in=room_ids,
    )


def stranded_rooms(
    *,
    anchor_room_id: int,
    room_ids: set[int],
    drop_room_id: int | None = None,
    drop_exit_ids: frozenset[int] = frozenset(),
) -> set[int]:
    """Ids in ``room_ids`` unreachable from ``anchor_room_id`` after a hypothetical drop.

    BFS over the exit graph restricted to ``room_ids``, skipping the dropped
    room / exits. Room graphs stay small (a building, or one area's worth of
    rooms), so this is cheap.
    """
    room_ids = set(room_ids)
    room_ids.discard(drop_room_id)
    if anchor_room_id not in room_ids:
        return set()
    adjacency: dict[int, set[int]] = {rid: set() for rid in room_ids}
    for exit_obj in exits_for_rooms(room_ids):
        if exit_obj.pk in drop_exit_ids:
            continue
        src, dst = exit_obj.db_location_id, exit_obj.db_destination_id
        if src in room_ids and dst in room_ids:
            adjacency[src].add(dst)
            adjacency[dst].add(src)
    seen = {anchor_room_id}
    frontier = [anchor_room_id]
    while frontier:
        current = frontier.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                frontier.append(neighbor)
    return room_ids - seen


def place_room_on_grid(*, profile: RoomProfile, grid_x: int, grid_y: int, floor: int) -> None:
    """Move a room to a grid cell, raising ``GridServiceError`` on collision.

    Placement never gates play — the one guard is cell collision on the
    target floor, so the map stays readable.
    """
    occupied = (
        RoomProfile.objects.filter(area=profile.area, grid_x=grid_x, grid_y=grid_y, floor=floor)
        .exclude(pk=profile.pk)
        .exists()
    )
    if occupied:
        msg = "That spot on the map is already occupied."
        raise GridServiceError(msg)
    profile.grid_x = grid_x
    profile.grid_y = grid_y
    profile.floor = floor
    profile.save(update_fields=["grid_x", "grid_y", "floor"])

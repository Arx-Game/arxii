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

from django.utils.text import slugify

from evennia_extensions.models import RoomProfile, RoomSizeTier
from world.areas.constants import GridOrigin

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB
    from evennia.objects.objects import DefaultObject

    from world.areas.models import Area


_EXIT_TYPECLASS = "typeclasses.exits.Exit"
_CHARACTER_TYPECLASS = "typeclasses.characters.Character"


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

    # create_object runs Room.at_object_creation, which get_or_creates a bare
    # RoomProfile; the update_or_create below then fills it. One extra write vs
    # the old bare-ObjectDB create, accepted to stay under the noqa ratchet and
    # keep typeclass init honest.
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

    # Unlike the old bare-ObjectDB create, create_object(location=...) fires
    # source.at_object_receive for the exit object. Room.at_object_receive's
    # gossip/tidings paths early-return for non-Characters and its scene
    # broadcast no-ops without live in-memory scene state, so this is benign —
    # traced in the #2449 Task 1 review.
    exit_obj = evennia_create.create_object(
        typeclass=_EXIT_TYPECLASS,
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
        db_typeclass_path=_EXIT_TYPECLASS,
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
        db_typeclass_path=_EXIT_TYPECLASS,
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


def has_character_occupants(room: ObjectDB) -> bool:
    return any(obj.is_typeclass(_CHARACTER_TYPECLASS, exact=False) for obj in room.contents)


def has_non_exit_contents(room: ObjectDB) -> bool:
    """Any character or item still in ``room`` — exits don't count.

    Exits are cleaned up as part of removal itself (see ``StaffRemoveRoomAction``),
    so they're not "contents" blocking it; a character or a stray item is.
    """
    return any(not obj.is_typeclass(_EXIT_TYPECLASS, exact=False) for obj in room.contents)


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


def _is_slug_segment(value: str) -> bool:
    """Whether ``value`` is exactly one non-empty slug segment (no ``/``)."""
    return bool(value) and slugify(value) == value


def _promote_room_to_authored(room_profile: RoomProfile, key: str) -> None:
    """Promote a room to AUTHORED, assigning its permanent ``<area-slug>/<room-slug>`` key.

    Beyond the ``<area-slug>/<room-slug>`` shape check, the ``<area-slug>`` segment
    must equal ``room_profile.area.slug`` exactly — a well-formed key naming the
    wrong area would otherwise be accepted silently and permanently (ADR-0140), while
    the exporter groups rooms by the room's actual FK, so the bundle filename and the
    key's prefix would disagree forever. If the room's area is AUTHORED but has no
    slug yet (AUTHORED areas can be slugless until they're promoted themselves), the
    area must be promoted first — there is no slug yet to compare against.
    """
    area_slug, _, room_slug = key.partition("/")
    if not room_slug or not _is_slug_segment(area_slug) or not _is_slug_segment(room_slug):
        msg = f"{key!r} is not a valid '<area-slug>/<room-slug>' fixture key."
        raise GridServiceError(msg)
    if room_profile.area is None or room_profile.area.origin != GridOrigin.AUTHORED:
        msg = (
            "This room's area must exist and be AUTHORED before the room can be "
            "promoted (a room whose area isn't AUTHORED can never export)."
        )
        raise GridServiceError(msg)
    if room_profile.area.slug is None:
        msg = "This room's area must be promoted (given a slug) before the room can be promoted."
        raise GridServiceError(msg)
    if area_slug != room_profile.area.slug:
        msg = (
            f"Fixture key {key!r} names area {area_slug!r}, but this room's area is "
            f"{room_profile.area.slug!r}."
        )
        raise GridServiceError(msg)
    if room_profile.fixture_key is not None and room_profile.fixture_key != key:
        msg = "This room already has a different fixture key; keys are permanent once set."
        raise GridServiceError(msg)
    room_profile.origin = GridOrigin.AUTHORED
    room_profile.fixture_key = key
    room_profile.save(update_fields=["origin", "fixture_key"])


def ensure_slug_change_allowed(area: Area, new_slug: str | None) -> str | None:
    """Refusal message when ``new_slug`` would re-slug an already-keyed area.

    Once an area has a slug, changing it is refused outright — regardless of
    the area's current ``origin``. An edit can touch ``slug`` without touching
    ``origin`` at all, so ``origin`` alone isn't a reliable "already exported"
    signal; the stricter, origin-independent rule is what actually protects an
    exported area's permanent key (shared by ``promote_to_authored`` and
    ``EditAreaAction``, #2449). Returns ``None`` when the change is allowed: no
    slug set yet, ``new_slug`` is ``None``, or it matches the existing slug.
    """
    if new_slug is None or area.slug is None or new_slug == area.slug:
        return None
    return "This area already has a different slug; keys are permanent once set."


def _promote_area_to_authored(area: Area, key: str) -> None:
    if not _is_slug_segment(key):
        msg = f"{key!r} is not a valid area slug."
        raise GridServiceError(msg)
    refusal = ensure_slug_change_allowed(area, key)
    if refusal is not None:
        raise GridServiceError(refusal)
    area.origin = GridOrigin.AUTHORED
    area.slug = key
    area.save(update_fields=["origin", "slug"])


def promote_to_authored(
    *, room_profile: RoomProfile | None = None, area: Area | None = None, key: str
) -> None:
    """Promote a PLAYER/STORY room or area to AUTHORED, assigning its permanent key.

    Exactly one of ``room_profile``/``area`` must be given. Validates the key
    format — ``<area-slug>/<room-slug>`` for a room, a plain slug for an area —
    and, for a room, enforces the slice-1 invariant that its area must exist and
    itself be AUTHORED (see ``core_management.grid_export.find_unhoused_authored_rooms``);
    otherwise the room would be silently unreachable to any export pass.

    Key permanence (ADR-0140): re-promoting with a *different* key than one
    already set raises — authored identity is assignment-time and permanent.
    Re-promoting with the *same* key is a no-op success.
    """
    if room_profile is not None and area is not None:
        msg = "Promote exactly one of room_profile or area, not both."
        raise GridServiceError(msg)
    if room_profile is not None:
        _promote_room_to_authored(room_profile, key)
    elif area is not None:
        _promote_area_to_authored(area, key)
    else:
        msg = "Promote exactly one of room_profile or area."
        raise GridServiceError(msg)


def suggest_fixture_key(area: Area, name: str) -> str:
    """Suggest a ``<area-slug>/<room-slug>`` fixture key for ``name`` in ``area``.

    Not a reservation — just a starting point for staff to accept or edit; the
    permanence contract lives in ``promote_to_authored``. ``area.slug`` must
    already be set (i.e. ``area`` is itself AUTHORED). Dedupes against existing
    fixture keys under this area's prefix with one ``startswith`` query, appending
    ``-2``, ``-3``, ... on collision.
    """
    if not area.slug:
        msg = "Can't suggest a fixture key for an area with no slug."
        raise GridServiceError(msg)
    base = f"{area.slug}/{slugify(name)}"
    prefix = f"{area.slug}/"
    existing = set(
        RoomProfile.objects.filter(fixture_key__startswith=prefix).values_list(
            "fixture_key", flat=True
        )
    )
    if base not in existing:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"

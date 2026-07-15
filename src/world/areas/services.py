from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import connection
from evennia.objects.models import ObjectDB

from evennia_extensions.models import RoomProfile
from world.areas.models import Area, AreaClosure
from world.societies.models import Society

if TYPE_CHECKING:
    from world.areas.constants import AreaLevel
    from world.realms.models import Realm
    from world.scenes.models import Scene


def get_ancestry(area: Area) -> list[Area]:
    """Return the full ancestor chain from root down to this area.

    Uses the AreaClosure materialized view for a single indexed query.
    """
    ancestor_pks = list(
        AreaClosure.objects.filter(descendant_id=area.pk)
        .order_by("-depth")
        .values_list("ancestor_id", flat=True)
    )
    if len(ancestor_pks) <= 1:
        return [area]
    ancestors_by_pk = {a.pk: a for a in Area.objects.filter(pk__in=ancestor_pks)}
    return [ancestors_by_pk[pk] for pk in ancestor_pks]


def get_ancestor_at_level(area: Area, target_level: AreaLevel) -> Area | None:
    """Walk the ancestry to find the ancestor at the given AreaLevel.

    Returns None if no ancestor exists at that level.
    """
    for ancestor in get_ancestry(area):
        if ancestor.level == target_level:
            return ancestor
    return None


# ---------------------------------------------------------------------------
# `where` — the public presence / navigation surface (#1463)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WhereEntry:
    """One ``where`` row: a present character's display name + its coloured room path."""

    persona_name: str
    room_path: str
    room_id: int


def _room_display_name(room: ObjectDB) -> str:
    """A room's display name (edited longname if any, else its key)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return room.display_data.get_display_name()
    except (AttributeError, ObjectDoesNotExist):
        return room.key


def colored_area_path(room: ObjectDB) -> str:
    """Render a room's full area-hierarchy path with per-area colours (#1463).

    Walks the area ancestry outermost→innermost; each area uses its own ``color`` or
    inherits the nearest coloured ancestor's, so a colour set on a region/house cascades
    down. Ends with the room's display name. Returns the plain room name when it has no
    area. Segments are joined by " - " (the Arx-1 shape).
    """
    room_name = _room_display_name(room)
    profile = room.room_profile_or_none
    if profile is None or profile.area is None:
        return room_name
    segments: list[str] = []
    current_color = ""
    for area in get_ancestry(profile.area):
        current_color = area.color or current_color
        segments.append(f"{current_color}{area.name}|n")
    segments.append(f"{current_color}{room_name}|n")
    return " - ".join(segments)


def where_listing(viewer_account: object | None = None) -> list[WhereEntry]:
    """Characters currently in PUBLIC rooms, with their coloured location paths (#1463).

    The pull/navigation surface of the public world — who's out and about to be RP'd with.
    Characters in non-public rooms (``RoomProfile.is_public=False``) or in no room are
    omitted, so private RP stays off ``where`` (the #1287 privacy invariant). One entry per
    character, keyed on its **active** persona (a TEMPORARY mask shows that face, by design),
    sorted by name. Quiet-mode characters (#1463) are omitted unless ``viewer_account`` is the
    player themselves or on their allowlist — though they still appear to others in the room
    itself; ``where`` is the at-a-distance surface quiet mode opts out of. A concealed character
    (#1225 — any active ``conceals_from_perception`` condition) is omitted unconditionally: unlike
    the room-occupant list, there is no per-observer "detection" concept for an anonymous global
    directory, and ``where`` additionally reveals the character's exact room path, so leaving
    concealment to per-viewer gating here would defeat the concealment system entirely.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415
    from evennia import SESSION_HANDLER  # noqa: PLC0415

    from evennia_extensions.models import room_is_publicly_listed  # noqa: PLC0415
    from world.conditions.services import is_concealed  # noqa: PLC0415
    from world.scenes.presence import hidden_from_viewer  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    seen: set[int] = set()
    entries: list[WhereEntry] = []
    for session in SESSION_HANDLER.get_sessions():
        puppet = session.puppet
        if puppet is None or puppet.id in seen:
            continue
        seen.add(puppet.id)
        if hidden_from_viewer(puppet, viewer_account):
            continue
        if is_concealed(puppet):
            continue
        room = puppet.location
        if room is None or not room_is_publicly_listed(room):
            continue
        try:
            sheet = puppet.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        persona = active_persona_for_sheet(sheet)
        entries.append(
            WhereEntry(
                persona_name=persona.name,
                room_path=colored_area_path(room),
                room_id=room.id,
            )
        )
    entries.sort(key=lambda entry: entry.persona_name.lower())
    return entries


def area_grid_path(area: Area) -> list[tuple[int | None, int | None]]:
    """Return the chain of parent-local (grid_x, grid_y) pairs from root to ``area``.

    Rendering-support primitive only (per this issue's Decision 2): each entry is
    that area's position within ITS OWN parent's local grid, not a resolved world
    coordinate — composing these into a global position is a future renderer's job,
    not this helper's. Entries are ``(None, None)`` for any area in the chain with
    unset coordinates; nothing here is consulted by ``find_route`` or any other
    routing code.
    """
    return [(ancestor.grid_x, ancestor.grid_y) for ancestor in get_ancestry(area)]


def get_effective_realm(area: Area) -> Realm | None:
    """Walk up the hierarchy to find the nearest realm assignment.

    Returns None if no ancestor has a realm set.
    """
    node: Area | None = area
    while node is not None:
        if node.realm_id is not None:
            return node.realm
        node = node.parent
    return None


def get_descendant_areas(area: Area) -> list[Area]:
    """Return all areas in the subtree below this area."""
    descendant_pks = list(
        AreaClosure.objects.filter(ancestor_id=area.pk, depth__gt=0).values_list(
            "descendant_id", flat=True
        )
    )
    return list(Area.objects.filter(pk__in=descendant_pks))


def get_rooms_in_area(area: Area) -> list[RoomProfile]:
    """Return all RoomProfiles in this area and everything beneath it."""
    all_area_pks = list(
        AreaClosure.objects.filter(ancestor_id=area.pk).values_list("descendant_id", flat=True)
    )
    return list(
        RoomProfile.objects.filter(area_id__in=all_area_pks).select_related("objectdb", "area")
    )


def area_subtree_pks(area: Area) -> list[int]:
    """Return pks of ``area`` and all its descendants.

    Uses the AreaClosure materialized view on Postgres. On SQLite (test
    cache) the view does not exist, so we walk the ``Area.parent`` hierarchy
    directly. Area trees are shallow, so the Python walk is cheap.
    """
    if connection.vendor == "postgresql":  # noqa: STRING_LITERAL
        return list(
            AreaClosure.objects.filter(ancestor_id=area.pk).values_list("descendant_id", flat=True)
        )

    # SQLite fallback: breadth-first walk of Area.parent.
    subtree: set[int] = {area.pk}
    frontier = [area.pk]
    while frontier:
        parent_ids = frontier
        frontier = []
        for child in Area.objects.filter(parent_id__in=parent_ids).only("pk", "parent_id"):
            if child.pk not in subtree:
                subtree.add(child.pk)
                frontier.append(child.pk)
    return list(subtree)


def reparent_area(area: Area, new_parent: Area | None) -> None:
    """Move an area under a new parent.

    The AreaClosure materialized view is refreshed automatically by Area.save(),
    so descendants' ancestry is always consistent after this call.
    """
    area.parent = new_parent
    area.save()


def get_room_profile(room_obj: ObjectDB) -> RoomProfile:
    """Get or create the RoomProfile for a room ObjectDB instance."""
    profile, _ = RoomProfile.objects.get_or_create(objectdb=room_obj)
    return profile


def area_for_scene(scene: Scene | None) -> Area | None:
    """Resolve the Area for a scene's location, or None.

    A ``Scene.location`` FK points at the room's bare ``ObjectDB`` — the room
    typeclass carries no ``.area`` attribute of its own; the Area lives on the
    room's ``RoomProfile`` (reverse OneToOne, accessor ``room_profile``, absent
    for a room with no profile row yet). Shared home for a walk that used to be
    inlined (and duplicated, untested) in two places: ``world.magic``'s
    ``services/gain.py`` (dramatic-moment renown award) and
    ``audere_majora._mint_crossing_deed`` — both wrote a bare
    ``scene.location.area`` that raised ``AttributeError`` on any scene whose
    location lacks a ``RoomProfile`` (#2183). ``world.magic`` already depends on
    ``world.areas`` at module level elsewhere (e.g.
    ``services/resonance_environment.py``); the reverse import would be a
    circular-import failure (``world.magic.models`` imports ``audere_majora`` at
    package-init time), so this module — not ``world.magic`` — is the safe home
    for the shared helper.
    """
    location = scene.location if scene is not None else None
    if location is None:
        return None
    profile = location.room_profile_or_none
    return profile.area if profile is not None else None


def societies_for_scene(scene: Scene) -> list[Society]:
    """Resolve which societies are relevant at a scene's location (#1464 walk fix).

    Permissive by default: ANY society sharing the nearest resolvable realm is
    relevant; a ``dominant_society`` on any ancestor (nearest-first) overrides.
    ``realm``/``dominant_society`` are set high in the tree (Kingdom/Region), so
    the walk climbs the parent chain from the room's immediate area — a room in
    a Building-level area no longer resolves to nobody. Parent-FK walk
    (identity-map cheap, no ``AreaClosure`` dependency — the #1765 jurisdiction
    idiom, so it behaves identically on the SQLite tier). Returns ``[]`` when
    the location, its RoomProfile, its area, or any realm cannot be resolved.
    Callers: fashion perception (checks), scandal reach minting (#1464).
    """
    area = area_for_scene(scene)
    if area is None:
        return []
    return societies_for_area(area)


def societies_for_area(area: Area | None) -> list[Society]:
    """Nearest-first ancestor walk: dominant society wins, else realm societies.

    Cycle-safe; the first node carrying ``dominant_society`` short-circuits to
    exactly that society, else the first node carrying ``realm`` yields every
    society of that realm.
    """
    seen: set[int] = set()
    node = area
    while node is not None and node.pk not in seen:
        if node.dominant_society_id is not None:
            return [node.dominant_society]
        if node.realm_id is not None:
            return list(Society.objects.filter(realm_id=node.realm_id))
        seen.add(node.pk)
        node = node.parent
    return []

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    profile = getattr(room, "room_profile", None)  # noqa: GETATTR_LITERAL — reverse OneToOne
    if profile is None or profile.area is None:
        return room_name
    segments: list[str] = []
    current_color = ""
    for area in get_ancestry(profile.area):
        current_color = area.color or current_color
        segments.append(f"{current_color}{area.name}|n")
    segments.append(f"{current_color}{room_name}|n")
    return " - ".join(segments)


def where_listing() -> list[WhereEntry]:
    """Characters currently in PUBLIC rooms, with their coloured location paths (#1463).

    The pull/navigation surface of the public world — who's out and about to be RP'd with.
    Characters in non-public rooms (``RoomProfile.is_public=False``) or in no room are
    omitted, so private RP stays off ``where`` (the #1287 privacy invariant). One entry per
    character, keyed on its **active** persona (a TEMPORARY mask shows that face, by design),
    sorted by name.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415
    from evennia import SESSION_HANDLER  # noqa: PLC0415

    from evennia_extensions.models import room_is_publicly_listed  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    seen: set[int] = set()
    entries: list[WhereEntry] = []
    for session in SESSION_HANDLER.get_sessions():
        puppet = getattr(session, "puppet", None)  # noqa: GETATTR_LITERAL
        if puppet is None or puppet.id in seen:
            continue
        seen.add(puppet.id)
        room = puppet.location
        if room is None or not room_is_publicly_listed(room):
            continue
        try:
            sheet = puppet.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        persona = active_persona_for_sheet(sheet)
        entries.append(WhereEntry(persona_name=persona.name, room_path=colored_area_path(room)))
    entries.sort(key=lambda entry: entry.persona_name.lower())
    return entries


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


def societies_for_scene(scene: Scene) -> list[Society]:
    """Resolve which societies' fashion is perceived in a scene's location.

    Permissive by default: ANY society sharing the location's area's realm is
    relevant. If the area names an explicit ``dominant_society``, only that one
    is relevant. Returns ``[]`` when the location, its RoomProfile, its area, or
    the area's realm cannot be resolved.
    """
    location = getattr(scene, "location", None)  # noqa: GETATTR_LITERAL
    if location is None:
        return []

    # room_profile is a reverse OneToOne; its accessor raises RelatedObjectDoesNotExist
    # (a subclass of AttributeError) when absent, so getattr-with-default is the idiom.
    profile = getattr(location, "room_profile", None)  # noqa: GETATTR_LITERAL
    if profile is None:
        return []

    area = profile.area
    if area is None:
        return []

    if area.dominant_society_id is not None:
        return [area.dominant_society]

    if area.realm_id is None:
        return []

    return list(Society.objects.filter(realm_id=area.realm_id))

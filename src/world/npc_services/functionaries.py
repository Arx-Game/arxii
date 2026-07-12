"""Functionary placement services (#1766).

A :class:`~world.npc_services.models.Functionary` is a class-1 NPC placed in a room — the
non-piloted anchor for that room's gameplay loops. These helpers place/remove functionaries
and answer the co-location question the interaction layer needs: *"which functionaries are
here, and does this query name one of them?"*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q, QuerySet

from world.npc_services.models import Functionary, NPCRole

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile


def functionaries_in_room(room_profile: RoomProfile) -> QuerySet[Functionary]:
    """Active functionaries present in *room_profile* (role also active)."""
    return Functionary.objects.filter(
        room=room_profile,
        is_active=True,
        role__is_active=True,
    ).select_related("role")


def functionaries_in_location(location: ObjectDB) -> QuerySet[Functionary]:
    """Active functionaries present in the room *location* (an ObjectDB), or an empty queryset.

    Resolves the room's :class:`RoomProfile` via ``areas.services.get_room_profile``; a
    ``None`` or non-``ObjectDB`` location (e.g. an unplaced caller) yields no functionaries.
    """
    from evennia.objects.models import ObjectDB as _ObjectDB  # noqa: PLC0415

    from world.areas.services import get_room_profile  # noqa: PLC0415

    if not isinstance(location, _ObjectDB):
        return Functionary.objects.none()
    return functionaries_in_room(get_room_profile(location))


def functionary_in_location(location: ObjectDB, query: str) -> Functionary | None:
    """Resolve one functionary matching *query* in the room *location*, or None.

    A ``None`` or non-``ObjectDB`` location yields ``None`` (the interaction layer then falls
    back to a global role lookup).
    """
    from evennia.objects.models import ObjectDB as _ObjectDB  # noqa: PLC0415

    from world.areas.services import get_room_profile  # noqa: PLC0415

    if not isinstance(location, _ObjectDB):
        return None
    return functionary_in_room(get_room_profile(location), query)


def functionary_in_room(room_profile: RoomProfile, query: str) -> Functionary | None:
    """Resolve one functionary present in *room_profile* by id, placement name, or role name.

    Matching order: numeric id → exact (name_override or role name, case-insensitive) →
    a unique ``icontains`` prefix. Returns ``None`` when nothing here matches.
    """
    present = functionaries_in_room(room_profile)
    query = query.strip()
    if query.isdigit():
        return present.filter(pk=int(query)).first()
    exact = present.filter(Q(name_override__iexact=query) | Q(role__name__iexact=query))
    if exact.exists():
        return exact.first()
    partial = present.filter(Q(name_override__icontains=query) | Q(role__name__icontains=query))
    # Only accept a partial match when it's unambiguous.
    if partial.count() == 1:
        return partial.first()
    return None


def place_functionary(
    *,
    role: NPCRole,
    room: RoomProfile,
    name_override: str = "",
    description_override: str = "",
) -> Functionary:
    """Place (or re-activate) a functionary of *role* in *room* — idempotent per (role, room)."""
    functionary, _ = Functionary.objects.update_or_create(
        role=role,
        room=room,
        defaults={
            "name_override": name_override,
            "description_override": description_override,
            "is_active": True,
        },
    )
    return functionary


def remove_functionary(*, role: NPCRole, room: RoomProfile) -> bool:
    """Soft-remove the (role, room) functionary (set inactive). True if one was present."""
    updated = Functionary.objects.filter(role=role, room=room, is_active=True).update(
        is_active=False
    )
    return updated > 0


def random_active_functionary() -> Functionary | None:
    """One random active Functionary (role also active), or ``None`` if there are none.

    The botch-outcome NPC picker for Identification (#1107 slice 5): a fumbled identification
    check fake-IDs a random Functionary rather than naming a PC (the spec's oracle rule — a botch
    must never out a real player). ``order_by("?")`` issues a Postgres ``ORDER BY RANDOM()`` —
    a full-table sort, but the Functionary table is small (a handful of NPC placements per room)
    so this is acceptable at this scale; revisit if the catalog grows large enough to matter.
    """
    return (
        Functionary.objects.filter(is_active=True, role__is_active=True)
        .select_related("role")
        .order_by("?")
        .first()
    )

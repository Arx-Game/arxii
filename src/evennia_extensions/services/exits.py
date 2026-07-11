"""Service helpers for Evennia exits (#2175)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia_extensions.constants import ExitKind, RoomEnclosure
from evennia_extensions.models import ExitProfile

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


#: Map a base room enclosure to the next-less-sheltered level when a window is open.
#: Sealed rooms ignore open windows; open-air rooms cannot get more open.
_ENCLOSURE_DOWNGRADE: dict[RoomEnclosure, RoomEnclosure] = {
    RoomEnclosure.SEALED: RoomEnclosure.SEALED,
    RoomEnclosure.WALLED: RoomEnclosure.ROOFED,
    RoomEnclosure.ROOFED: RoomEnclosure.OPEN_AIR,
    RoomEnclosure.OPEN_AIR: RoomEnclosure.OPEN_AIR,
}


def is_window(exit_obj: ObjectDB) -> bool:
    """Return True if the exit is a window."""
    profile = ExitProfile.get_or_create_for_exit(exit_obj)
    return profile.exit_kind == ExitKind.WINDOW


def set_window_open(exit_obj: ObjectDB, is_open: bool) -> None:
    """Set a window's open/closed state. No-op if the exit is not a window."""
    profile = ExitProfile.get_or_create_for_exit(exit_obj)
    if profile.exit_kind != ExitKind.WINDOW:
        return
    profile.is_open = is_open
    profile.save(update_fields=["is_open"])


def effective_enclosure_for_room(room_obj: ObjectDB) -> RoomEnclosure:
    """Return the room's effective enclosure, treating open windows as a breach.

    A single open window in the room downgrades the base enclosure by one step
    for weather-axis sheltering. Temperature axes (COLD/HEAT) are unaffected
    separately; callers use this value only for the weather-axis gate.
    """
    try:
        room_profile = room_obj.room_profile
    except AttributeError:
        room_profile = None
    base = room_profile.enclosure if room_profile else RoomEnclosure.OPEN_AIR
    try:
        exits = room_obj.exits
    except AttributeError:
        exits = []
    for exit_obj in exits:
        profile = ExitProfile.objects.filter(objectdb=exit_obj).first()
        if profile and profile.exit_kind == ExitKind.WINDOW and profile.is_open:
            return _ENCLOSURE_DOWNGRADE[base]
    return base

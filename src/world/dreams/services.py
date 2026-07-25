"""Dream realm service functions (#2290)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def get_dream_space(*, room: ObjectDB) -> ObjectDB | None:  # noqa: OBJECTDB_PARAM
    """Return the dream room for a physical waking room.

    Returns the DreamReflection's dream_room if one exists and is active;
    falls back to the liminal dream room (#2287) if not.

    Returns an **ObjectDB** deliberately, even though `DreamReflection.dream_room`
    is a RoomProfile since #2608: three of the four callers (`look` perception,
    `Character.msg_room_state`, the dreamwalk action) want a room object to
    perceive or move into, and only `is_dream_engaged` wants a profile — and it
    gets there with a pk lookup, since RoomProfile shares ObjectDB's pk. Handing
    back the profile would push a `.objectdb` hop onto the majority.

    Args:
        room: An ObjectDB room instance (the physical waking room) — the
            caller almost always holds ``character.location``.

    Returns:
        The ObjectDB dream room to perceive, or None on an unseeded database.
    """
    from world.dreams.models import DreamReflection  # noqa: PLC0415

    reflection = DreamReflection.objects.for_waking_room(room)
    if reflection is not None:
        return reflection.dream_room.objectdb
    from world.vitals.services import get_dream_room  # noqa: PLC0415

    return get_dream_room()

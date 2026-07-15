"""Dream realm service functions (#2290)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def get_dream_space(*, room: ObjectDB) -> ObjectDB | None:  # noqa: OBJECTDB_PARAM
    """Return the dream room for a physical waking room.

    Returns the DreamReflection's dream_room if one exists and is active;
    falls back to the liminal dream room (#2287) if not.

    Args:
        room: An ObjectDB room instance (the physical waking room).

    Returns:
        The ObjectDB dream room to perceive, or None on an unseeded database.
    """
    from world.dreams.models import DreamReflection  # noqa: PLC0415

    reflection = DreamReflection.objects.for_waking_room(room)
    if reflection is not None:
        return reflection.dream_room
    from world.vitals.services import get_dream_room  # noqa: PLC0415

    return get_dream_room()

"""Dream realm seed content (#2290).

Seeds:
- Deep dreaming Area (PLANE level) with a starter room
- Dream-specific DamageType rows (Nightmare, Dread, Confusion)
- Master seed function ``ensure_dream_content()``
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from world.areas.constants import AreaLevel
from world.areas.models import Area
from world.dreams.constants import (
    DEEP_DREAMING_AREA_NAME,
    DEEP_DREAMING_STARTER_ROOM_KEY,
    DREAM_DAMAGE_TYPES,
)


def ensure_deep_dreaming_area() -> Area:
    """Ensure the deep dreaming PLANE-level Area + starter room exist.

    Returns the Area instance. The starter room is created as a plain
    Evennia Room with the deep dreaming area as its RoomProfile's area.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    area, _ = Area.objects.get_or_create(
        name=DEEP_DREAMING_AREA_NAME,
        defaults={
            "level": AreaLevel.PLANE,
            "description": (
                "A realm of raw dream-stuff, detached from the waking world. "
                "The landscape shifts and reforms with terrifying speed."
            ),
        },
    )

    # Ensure starter room exists
    room = ObjectDB.objects.filter(db_key=DEEP_DREAMING_STARTER_ROOM_KEY).first()
    if room is None:
        from evennia.utils import create as evennia_create  # noqa: PLC0415

        room = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room",
            key=DEEP_DREAMING_STARTER_ROOM_KEY,
            nohome=True,
        )
        room.db.desc = (
            "Wisps of grey mist curl around your feet, obscuring the ground. "
            "The air tastes of forgotten memories. Exits appear and dissolve "
            "in the corner of your eye, leading to places that may not exist."
        )

    # Link the starter room to the deep dreaming area via RoomProfile
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    profile, _created = RoomProfile.objects.get_or_create(
        objectdb=room,
        defaults={"area": area, "is_public": False},
    )
    if profile.area is None:
        profile.area = area
        profile.save(update_fields=["area"])

    return area


def ensure_dream_damage_types() -> None:
    """Ensure dream-specific DamageType rows exist."""
    from world.conditions.models import DamageType  # noqa: PLC0415

    descriptions = {
        "Nightmare": "Mental damage from dream horrors — the stuff of nightmares made real.",
        "Dread": "An overwhelming sense of dread that erodes mental composure.",
        "Confusion": "Disorienting dream-logic that scrambles the mind.",
    }
    for name in DREAM_DAMAGE_TYPES:
        DamageType.objects.get_or_create(
            name=name,
            defaults={"description": descriptions.get(name, "Dream-specific damage.")},
        )


def ensure_dream_content() -> None:
    """Master seed function for all dream realm content.

    Idempotent — safe to call multiple times. Seeds:
    - Sleeping condition (via vitals seed cluster)
    - Dream conditions (Nightmares, Madness, DreamPerilConfig)
    - Dream Peril consequence pool
    - Dream damage types
    - Deep dreaming area + starter room
    """
    from world.dreams.conditions import ensure_dream_conditions  # noqa: PLC0415
    from world.vitals.factories import create_dream_peril_pool  # noqa: PLC0415
    from world.vitals.seeds import ensure_sleeping_condition  # noqa: PLC0415

    ensure_sleeping_condition()
    ensure_dream_conditions()
    create_dream_peril_pool()
    ensure_dream_damage_types()
    ensure_deep_dreaming_area()

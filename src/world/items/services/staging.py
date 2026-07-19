"""GM improv prop staging (#2503) — the mid-scene "are there torches in here?" verb.

A GM stages an existing ``ItemTemplate`` directly into a room, no holder — the
same shape as ``narrative_grants.grant_touchstone_item_to_character`` (row-then-
materialize), but materialized straight into a room via
``materialize.materialize_item_game_object_in_room`` instead of a character's
inventory. Because it rides the same chokepoint, a staged torch gets the same
template-default ``ObjectProperty`` rows (``flammable``, ...) as a crafted or
looted torch of the same template — Task 3's bare-object ``get_available_actions``
scan picks it up automatically, with no bespoke wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.items.models import ItemTemplate


def stage_prop(item_template: ItemTemplate, room: ObjectDB) -> ObjectDB:  # noqa: OBJECTDB_PARAM
    """Instantiate ``item_template`` as a physical, holder-less prop in ``room``.

    Args:
        item_template: The curated archetype to instantiate (existing rows only —
            callers resolve this by exact name before calling in; this function
            does no name lookup of its own).
        room: The room the prop materializes in.

    Returns:
        The new prop's ``ObjectDB``.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.services.materialize import (  # noqa: PLC0415
        materialize_item_game_object_in_room,
    )

    instance = ItemInstance.objects.create(template=item_template)
    return materialize_item_game_object_in_room(instance, room)

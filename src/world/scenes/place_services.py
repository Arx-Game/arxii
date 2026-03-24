"""Service functions for place management within scenes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.constants import ScenePrivacyMode
from world.scenes.models import Scene
from world.scenes.place_models import Place, PlacePresence

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona


def ensure_scene_for_location(
    room: ObjectDB,
    *,
    name: str | None = None,
) -> Scene:
    """Get or create an active scene for the given room.

    If an active scene already exists for the room, returns it.
    Otherwise creates a new public scene.

    Args:
        room: The room to ensure a scene for.
        name: Optional name for a new scene. Defaults to room name.

    Returns:
        The active Scene for this room.
    """
    existing = Scene.objects.filter(location=room, is_active=True).first()
    if existing is not None:
        return existing

    scene_name = name or f"Scene at {room.key}"
    return Scene.objects.create(
        name=scene_name,
        location=room,
        privacy_mode=ScenePrivacyMode.PUBLIC,
    )


def join_place(
    *,
    place: Place,
    persona: Persona,
) -> PlacePresence:
    """Add a persona to a place, removing them from any other place in the room.

    Args:
        place: The place to join.
        persona: The persona joining.

    Returns:
        The PlacePresence record.
    """
    if place.room_id is not None:
        # Remove from any other places in the same room
        PlacePresence.objects.filter(
            persona=persona,
            place__room_id=place.room_id,
        ).exclude(place=place).delete()

    presence, _created = PlacePresence.objects.get_or_create(
        place=place,
        persona=persona,
    )
    return presence


def clear_place_presence_for_character(character: ObjectDB) -> int:
    """Remove all PlacePresence records for a character.

    Called when a character leaves a room or moves to a different room.
    Returns the number of records deleted.
    """
    from world.scenes.models import Persona as PersonaModel  # noqa: PLC0415

    persona_ids = PersonaModel.objects.filter(
        character_identity__character=character,
    ).values_list("pk", flat=True)

    count, _ = PlacePresence.objects.filter(
        persona_id__in=persona_ids,
    ).delete()
    return count


def leave_place(
    *,
    place: Place,
    persona: Persona,
) -> bool:
    """Remove a persona from a place.

    Args:
        place: The place to leave.
        persona: The persona leaving.

    Returns:
        True if the persona was present and removed, False otherwise.
    """
    deleted, _ = PlacePresence.objects.filter(
        place=place,
        persona=persona,
    ).delete()
    return deleted > 0

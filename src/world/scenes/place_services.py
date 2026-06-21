"""Service functions for place management within scenes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.constants import ScenePrivacyMode
from world.scenes.models import Scene
from world.scenes.place_models import Place, PlacePresence

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona


def ensure_scene_for_location(
    room: ObjectDB,
    *,
    name: str | None = None,
    privacy_mode: ScenePrivacyMode | None = None,
) -> Scene:
    """Get or create an active scene for the given room.

    Thin wrapper over :func:`ensure_scene_for_location_created` that discards the
    created-signal for callers that only need the scene.
    """
    scene, _created = ensure_scene_for_location_created(room, name=name, privacy_mode=privacy_mode)
    return scene


def ensure_scene_for_location_created(
    room: ObjectDB,
    *,
    name: str | None = None,
    privacy_mode: ScenePrivacyMode | None = None,
) -> tuple[Scene, bool]:
    """Get or create an active scene for the given room, reporting newness.

    If an active scene already exists for the room, returns it (its existing
    privacy is preserved; ``privacy_mode`` is ignored). Otherwise creates a new
    scene with ``privacy_mode`` (derived from the room when not supplied).

    Args:
        room: The room to ensure a scene for.
        name: Optional name for a new scene. Defaults to room name.
        privacy_mode: Privacy for a newly-created scene. When omitted, derived
            from the room — PUBLIC if publicly listed, else PRIVATE.

    Returns:
        A ``(scene, created)`` tuple. ``created`` is True only when this call
        created the scene (so the caller may set an owner on it).
    """
    existing = Scene.objects.filter(location=room, is_active=True).first()
    if existing is not None:
        return existing, False

    if privacy_mode is None:
        from evennia_extensions.models import room_is_publicly_listed  # noqa: PLC0415

        privacy_mode = (
            ScenePrivacyMode.PUBLIC if room_is_publicly_listed(room) else ScenePrivacyMode.PRIVATE
        )

    scene_name = name or f"Scene at {room.key}"
    scene = Scene.objects.create(
        name=scene_name,
        location=room,
        privacy_mode=privacy_mode,
    )

    # Auto-engage Durance covenant for room occupants when a new scene starts (Slice B §4.10)
    from world.covenants.services import evaluate_scene_engagement  # noqa: PLC0415

    for obj in room.contents:
        sheet = getattr(obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is not None:
            evaluate_scene_engagement(character_sheet=sheet, room=room)

    return scene, True


def start_or_join_scene(
    room: ObjectDB,
    *,
    owner_account: AccountDB | None = None,
    name: str | None = None,
    privacy_mode: ScenePrivacyMode | None = None,
) -> Scene:
    """Implicitly start a scene in ``room`` (or join the existing one).

    Frictionless scene start (#1309): when a player acts in a room with no
    active scene, get-or-create one. When *this* call created the scene and an
    ``owner_account`` is supplied, that account is recorded as the scene owner
    (mirrors :meth:`SceneViewSet.perform_create`). If the scene already existed,
    no owner is changed — the actor simply joins.

    Idempotent: a second actor in the same room joins the same scene and is not
    made owner.

    Args:
        room: The room to start/join a scene in.
        owner_account: The acting player's account. Recorded as owner only on
            create. When None, no owner participation is written.
        name: Optional name for a newly-created scene.
        privacy_mode: Privacy for a newly-created scene (derived from the room
            when omitted).

    Returns:
        The active Scene for this room.
    """
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    scene, created = ensure_scene_for_location_created(room, name=name, privacy_mode=privacy_mode)
    if created and owner_account is not None:
        SceneParticipation.objects.get_or_create(
            scene=scene,
            account=owner_account,
            defaults={"is_owner": True},
        )
    return scene


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
        character_sheet__character=character,
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

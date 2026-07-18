from django.db import transaction
from django.utils import timezone
from evennia.objects.models import ObjectDB
from evennia.utils.create import create_object

from evennia_extensions.models import ObjectDisplayData, RoomProfile
from world.character_sheets.models import CharacterSheet
from world.gm.models import GMProfile
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.scenes.models import Scene


def spawn_instanced_room(  # noqa: PLR0913 — one owner-kind arg per caller (player vs GM)
    name: str,
    description: str,
    owner: CharacterSheet | None,
    return_location: ObjectDB | None,
    source_key: str = "",
    gm_owner: GMProfile | None = None,
) -> ObjectDB:
    """Create a temporary instanced room, its RoomProfile, and lifecycle record.

    Temporary instanced rooms are never publicly listed — the profile always
    ends with ``is_public=False``, regardless of the model default, so a GM
    scene room, mission room, or captivity room never leaks into public room
    browsing or derives a PUBLIC scene privacy from a stale default.
    """
    room = create_object(
        typeclass="typeclasses.rooms.Room",
        key=name,
        nohome=True,
    )
    profile, _created = RoomProfile.objects.get_or_create(objectdb=room)
    RoomProfile.objects.filter(pk=profile.pk).update(is_public=False)
    profile.is_public = False
    display_data, _created = ObjectDisplayData.objects.get_or_create(object=room)
    display_data.permanent_description = description
    display_data.save(update_fields=["permanent_description"])
    InstancedRoom.objects.create(
        room=room,
        owner=owner,
        gm_owner=gm_owner,
        return_location=return_location,
        source_key=source_key,
    )
    return room


def complete_instanced_room(room: ObjectDB) -> None:
    """Mark room completed, relocate occupants, delete if no history."""
    with transaction.atomic():
        instance = InstancedRoom.objects.select_for_update().get(room=room)
        if instance.status == InstanceStatus.COMPLETED:
            return
        instance.status = InstanceStatus.COMPLETED
        instance.completed_at = timezone.now()
        instance.save()

    # Determine return destination
    fallback = instance.return_location
    if fallback is None and instance.owner is not None:
        fallback = instance.owner.character.home

    # Relocate puppeted characters
    if fallback is not None:
        for obj in room.contents:
            if hasattr(obj, "sessions") and obj.sessions.all():
                obj.move_to(fallback, quiet=True)

    # Keep room if meaningful data exists, delete if ephemeral
    if not _has_meaningful_data(room):
        room.delete()


def _has_meaningful_data(room: ObjectDB) -> bool:
    """Check if this room has data worth preserving."""
    return Scene.objects.filter(location=room).exists()

from django.db import transaction
from django.utils import timezone
from evennia.objects.models import ObjectDB
from evennia.utils.create import create_object

from evennia_extensions.models import ObjectDisplayData
from world.character_sheets.models import CharacterSheet
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.scenes.models import Scene


def spawn_instanced_room(
    name: str,
    description: str,
    owner: CharacterSheet,
    return_location: ObjectDB | None,
    source_key: str = "",
) -> ObjectDB:
    """Create a temporary instanced room and its lifecycle record."""
    room = create_object(
        typeclass="typeclasses.rooms.Room",
        key=name,
        nohome=True,
    )
    display_data, _created = ObjectDisplayData.objects.get_or_create(object=room)
    display_data.permanent_description = description
    display_data.save(update_fields=["permanent_description"])
    InstancedRoom.objects.create(
        room=room,
        owner=owner,
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

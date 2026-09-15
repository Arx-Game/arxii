from django.db import transaction
from django.utils import timezone
from evennia.objects.models import ObjectDB
from evennia.utils.create import create_object

from evennia_extensions.models import ExitProfile, ObjectDisplayData, RoomProfile
from world.areas.models import Area
from world.character_sheets.models import CharacterSheet
from world.gm.models import GMProfile
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.scenes.models import Scene


def spawn_instanced_room(  # noqa: PLR0913 — one owner-kind arg per caller (player vs GM)
    name: str,
    description: str,
    owner: CharacterSheet | None,
    return_location: ObjectDB | None,  # noqa: OBJECTDB_PARAM — see InstancedRoom.return_location
    source_key: str = "",
    gm_owner: GMProfile | None = None,
    anchor_room: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM - sibling of return_location
    area: Area | None = None,
) -> ObjectDB:
    """Create a temporary instanced room, its RoomProfile, and lifecycle record.

    Temporary instanced rooms are never publicly listed — the profile always
    ends with ``is_public=False``, regardless of the model default, so a GM
    scene room, mission room, or captivity room never leaks into public room
    browsing or derives a PUBLIC scene privacy from a stale default.

    Area inheritance (#696 gap 7): the spawned profile's area is the explicit
    ``area`` when given (the authored override, or a task-target domain's area
    the caller resolved), else ``anchor_room``'s area, else None.

    When ``anchor_room`` is given, a one-way entrance exit is created from it
    into the spawned room, gated by the ``instance_entrance`` behavior package
    (run participants + GM owner only) and recorded on
    ``InstancedRoom.entrance_exit``; ``complete_instanced_room`` deletes it.
    """
    room = create_object(
        typeclass="typeclasses.rooms.Room",
        key=name,
        nohome=True,
    )
    profile, _created = RoomProfile.objects.get_or_create(objectdb=room)
    if area is None and anchor_room is not None:
        anchor_profile = anchor_room.room_profile_or_none
        if anchor_profile is not None:
            area = anchor_profile.area
    RoomProfile.objects.filter(pk=profile.pk).update(is_public=False, area=area)
    profile.is_public = False
    profile.area = area
    display_data, _created = ObjectDisplayData.objects.get_or_create(object=room)
    display_data.permanent_description = description
    display_data.save(update_fields=["permanent_description"])
    entrance_profile = None
    if anchor_room is not None:
        entrance_profile = _create_entrance(anchor_room=anchor_room, room=room)
    InstancedRoom.objects.create(
        room=profile,
        owner=owner,
        gm_owner=gm_owner,
        return_location=return_location,
        source_key=source_key,
        entrance_exit=entrance_profile,
    )
    return room


def _create_entrance(*, anchor_room: ObjectDB, room: ObjectDB) -> ExitProfile:
    """One-way entrance exit anchor_room→room, package-gated to the run (#696 gap 7)."""
    # Lazy: behaviors.instance_entrance_package pulls in the flows state layer.
    from behaviors.instance_entrance_package import (  # noqa: PLC0415
        INSTANCE_ENTRANCE_HOOK_PATH,
        INSTANCE_ENTRANCE_PACKAGE,
    )
    from behaviors.models import (  # noqa: PLC0415
        BehaviorPackageDefinition,
        BehaviorPackageInstance,
    )
    from world.areas.grid_services import create_one_way_exit  # noqa: PLC0415

    exit_obj = create_one_way_exit(
        name=room.db_key or "entrance",
        source=anchor_room,
        destination=room,
    )
    definition, _created = BehaviorPackageDefinition.objects.get_or_create(
        name=INSTANCE_ENTRANCE_PACKAGE,
        defaults={"service_function_path": INSTANCE_ENTRANCE_HOOK_PATH},
    )
    BehaviorPackageInstance.objects.create(
        definition=definition,
        obj=exit_obj,
        hook="can_traverse",
    )
    return ExitProfile.get_or_create_for_exit(exit_obj)


def complete_instanced_room(room: ObjectDB) -> None:
    """Mark room completed, relocate occupants, delete if no history."""
    with transaction.atomic():
        instance = InstancedRoom.objects.select_for_update().get(room_id=room.pk)
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

    # Tear down the temporary entrance exit (#696 gap 7). Deleting the exit
    # object cascades its ExitProfile; the FK is SET_NULL, so mirror that on
    # the cached instance rather than leaving a stale id in the identity map.
    if instance.entrance_exit_id is not None:
        instance.entrance_exit.objectdb.delete()
        instance.entrance_exit = None

    # Keep room if meaningful data exists, delete if ephemeral
    if not _has_meaningful_data(room):
        room.delete()


def _has_meaningful_data(room: ObjectDB) -> bool:
    """Check if this room has data worth preserving."""
    return Scene.objects.filter(location=room).exists()

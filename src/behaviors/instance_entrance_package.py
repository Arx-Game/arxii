"""Traversal gate for temporary instance entrances (#696 gap 7).

An instance entrance is the one-way exit ``spawn_instanced_room`` creates from
an anchor room into a spawned instanced room. This package's ``can_traverse``
hook admits only the people the run belongs to; the room-state serializer
hides the exit from everyone else via :func:`entrance_refuses` (see
``flows/service_functions/serializers/room_state.py``), so bystanders in the
anchor room never see a doorway they could not use.

Attach (done by ``world.instances.services.spawn_instanced_room``):
    ````python
    definition, _ = BehaviorPackageDefinition.objects.get_or_create(
        name=INSTANCE_ENTRANCE_PACKAGE,
        defaults={
            "service_function_path": (
                "behaviors.instance_entrance_package.restrict_to_run"
            ),
        },
    )
    BehaviorPackageInstance.objects.create(
        definition=definition, obj=exit_obj, hook="can_traverse"
    )
    ````
"""

from typing import TYPE_CHECKING

from behaviors.models import BehaviorPackageInstance
from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.instances.models import InstancedRoom

INSTANCE_ENTRANCE_PACKAGE = "instance_entrance"
INSTANCE_ENTRANCE_HOOK_PATH = "behaviors.instance_entrance_package.restrict_to_run"


def _instance_for_room(destination: "ObjectDB | None") -> "InstancedRoom | None":
    """The InstancedRoom lifecycle record for ``destination``, if any.

    RoomProfile shares ObjectDB's pk, so ``room_id=destination.pk`` resolves
    without fetching the profile first.
    """
    from world.instances.models import InstancedRoom  # noqa: PLC0415

    if destination is None:
        return None
    return InstancedRoom.objects.filter(room_id=destination.pk).first()


def _admits(instance: "InstancedRoom", actor_obj: "ObjectDB") -> bool:
    """Whether ``actor_obj`` belongs to the run behind ``instance``.

    Admitted: the instance's owning character, any participant of the mission
    run that spawned the room, and the GM owner (matched by account - a
    GMProfile is account-scoped, so any character that GM pilots qualifies).
    """
    sheet = actor_obj.character_sheet
    if sheet is not None:
        if instance.owner_id == sheet.pk:
            return True
        from world.missions.models import MissionParticipant  # noqa: PLC0415

        if MissionParticipant.objects.filter(
            instance__spawned_room_id=instance.room_id,
            character_id=sheet.pk,
        ).exists():
            return True
    if instance.gm_owner_id is not None:
        account_id = actor_obj.db_account_id
        if account_id is not None and instance.gm_owner.account_id == account_id:
            return True
    return False


def entrance_refuses(destination: "ObjectDB | None", actor_obj: "ObjectDB") -> bool:
    """True when ``destination`` is an instanced room that refuses ``actor_obj``.

    The serializer-side twin of :func:`restrict_to_run`: a non-instance
    destination refuses nobody, so ordinary exits are untouched.
    """
    instance = _instance_for_room(destination)
    if instance is None:
        return False
    return not _admits(instance, actor_obj)


def restrict_to_run(
    state: BaseState,
    pkg: BehaviorPackageInstance,
    actor: BaseState | None,
) -> bool:
    """``can_traverse`` hook: only the run's people may use an instance entrance.

    Refuses (returns False) when there is no actor, and when the destination's
    lifecycle record is gone (a defunct doorway awaiting teardown) - an
    entrance is never a public exit.
    """
    if actor is None:
        return False
    instance = _instance_for_room(state.obj.destination)
    if instance is None:
        return False
    return _admits(instance, actor.obj)

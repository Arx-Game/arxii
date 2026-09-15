"""Temporary instance entrances and area inheritance (#696 gap 7).

Covers: the one-way anchor->room entrance exit (created, recorded on
``InstancedRoom.entrance_exit``, package-gated), traversal admission (owner,
mission participant, GM owner in; bystander out), serializer-level visibility
(the entrance is absent from a refused looker's room payload), the three-step
area inheritance order at the service level (explicit area beats the anchor's
area beats None; the task-domain leg is a caller concern, tested at the
mission-resolution call site), and teardown deleting the entrance.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from behaviors.models import BehaviorPackageInstance
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from flows.factories import SceneDataManagerFactory
from flows.service_functions.serializers.room_state import RoomStatePayloadSerializer
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.instances.models import InstancedRoom
from world.instances.services import complete_instanced_room, spawn_instanced_room
from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory

_EXIT_TYPECLASS = "typeclasses.exits.Exit"


def _room(name: str) -> ObjectDB:
    return ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")


def _pc(room: ObjectDB) -> ObjectDB:
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    character.db_location = room
    character.save(update_fields=["db_location"])
    return character


def _entrance_exit(anchor: ObjectDB) -> ObjectDB:
    return ObjectDB.objects.get(db_typeclass_path=_EXIT_TYPECLASS, db_location=anchor)


class SpawnEntranceTests(TestCase):
    """Spawning with an anchor mints the recorded one-way doorway."""

    def setUp(self) -> None:
        self.anchor = _room("Inn Hallway")
        self.owner = _pc(self.anchor)
        self.spawned = spawn_instanced_room(
            name="Darkened Interior",
            description="PLACEHOLDER a ransacked parlor",
            owner=self.owner.sheet_data,
            return_location=self.anchor,
            source_key="test:entrance",
            anchor_room=self.anchor,
        )

    def test_one_way_exit_created_and_recorded(self) -> None:
        entrance = _entrance_exit(self.anchor)
        assert entrance.db_destination_id == self.spawned.pk
        # One-way: nothing leads back out of the instance.
        assert not ObjectDB.objects.filter(
            db_typeclass_path=_EXIT_TYPECLASS, db_location=self.spawned
        ).exists()
        instance = InstancedRoom.objects.get(room_id=self.spawned.pk)
        assert instance.entrance_exit_id == entrance.pk

    def test_entrance_package_attached(self) -> None:
        entrance = _entrance_exit(self.anchor)
        pkg = BehaviorPackageInstance.objects.get(obj=entrance, hook="can_traverse")
        assert pkg.definition.name == "instance_entrance"
        assert pkg.definition.service_function_path == (
            "behaviors.instance_entrance_package.restrict_to_run"
        )

    def test_anchorless_spawn_has_no_entrance(self) -> None:
        room = spawn_instanced_room(
            name="Floating Void",
            description="",
            owner=self.owner.sheet_data,
            return_location=None,
            source_key="test:anchorless",
        )
        instance = InstancedRoom.objects.get(room_id=room.pk)
        assert instance.entrance_exit_id is None
        assert not ObjectDB.objects.filter(
            db_typeclass_path=_EXIT_TYPECLASS, db_destination=room
        ).exists()


class EntranceTraversalTests(TestCase):
    """can_traverse admits only the run's people."""

    def setUp(self) -> None:
        self.anchor = _room("Inn Hallway")
        self.owner = _pc(self.anchor)
        self.participant = _pc(self.anchor)
        self.bystander = _pc(self.anchor)
        self.spawned = spawn_instanced_room(
            name="Darkened Interior",
            description="",
            owner=self.owner.sheet_data,
            return_location=self.anchor,
            source_key="test:traversal",
            anchor_room=self.anchor,
        )
        mission = MissionInstanceFactory(spawned_room_id=self.spawned.pk)
        MissionParticipantFactory(instance=mission, character=self.participant.sheet_data)
        self.entrance = _entrance_exit(self.anchor)
        self.context = SceneDataManagerFactory()
        for obj in (
            self.anchor,
            self.spawned,
            self.entrance,
            self.owner,
            self.participant,
            self.bystander,
        ):
            self.context.initialize_state_for_object(obj)
        self.exit_state = self.context.get_state_by_pk(self.entrance.pk)

    def _state(self, character: ObjectDB):
        return self.context.get_state_by_pk(character.pk)

    def test_owner_may_traverse(self) -> None:
        assert self.exit_state.can_traverse(self._state(self.owner)) is True

    def test_mission_participant_may_traverse(self) -> None:
        assert self.exit_state.can_traverse(self._state(self.participant)) is True

    def test_bystander_may_not_traverse(self) -> None:
        assert self.exit_state.can_traverse(self._state(self.bystander)) is False

    def test_gm_owner_may_traverse(self) -> None:
        gm = GMProfileFactory()
        gm_character = _pc(self.anchor)
        gm_character.db_account = gm.account
        gm_character.save(update_fields=["db_account"])
        room = spawn_instanced_room(
            name="GM Parlor",
            description="",
            owner=None,
            return_location=None,
            source_key=f"gm:{gm.pk}",
            gm_owner=gm,
            anchor_room=self.spawned,
        )
        entrance = ObjectDB.objects.get(
            db_typeclass_path=_EXIT_TYPECLASS, db_location=self.spawned, db_destination=room
        )
        for obj in (room, entrance, gm_character):
            self.context.initialize_state_for_object(obj)
        exit_state = self.context.get_state_by_pk(entrance.pk)
        assert exit_state.can_traverse(self._state(gm_character)) is True
        assert exit_state.can_traverse(self._state(self.bystander)) is False


class EntranceVisibilityTests(TestCase):
    """The room payload omits the entrance for anyone the package refuses."""

    def setUp(self) -> None:
        self.anchor = _room("Inn Hallway")
        self.owner = _pc(self.anchor)
        self.bystander = _pc(self.anchor)
        self.spawned = spawn_instanced_room(
            name="Darkened Interior",
            description="",
            owner=self.owner.sheet_data,
            return_location=self.anchor,
            source_key="test:visibility",
            anchor_room=self.anchor,
        )
        self.entrance = _entrance_exit(self.anchor)
        self.context = SceneDataManagerFactory()
        for obj in (self.anchor, self.spawned, self.entrance, self.owner, self.bystander):
            self.context.initialize_state_for_object(obj)
        self.room_state = self.context.get_state_by_pk(self.anchor.pk)

    def _exit_dbrefs_for(self, character: ObjectDB) -> set[str]:
        caller_state = self.context.get_state_by_pk(character.pk)
        serializer = RoomStatePayloadSerializer(
            None, context={"caller": caller_state, "room": self.room_state}
        )
        _chars, _objs, exits, _place = serializer._serialize_contents(self.room_state, caller_state)
        return {entry["dbref"] for entry in exits}

    def test_participant_sees_entrance(self) -> None:
        assert self.entrance.dbref in self._exit_dbrefs_for(self.owner)

    def test_bystander_does_not_see_entrance(self) -> None:
        assert self.entrance.dbref not in self._exit_dbrefs_for(self.bystander)


class AreaInheritanceTests(TestCase):
    """Explicit area beats the anchor's area beats None."""

    def setUp(self) -> None:
        self.anchor = _room("Inn Hallway")
        self.owner = _pc(self.anchor)
        self.anchor_area = AreaFactory(name="anchor-ward")
        RoomProfile.objects.update_or_create(
            objectdb=self.anchor, defaults={"area": self.anchor_area}
        )

    def _spawn(self, **kwargs) -> ObjectDB:
        return spawn_instanced_room(
            name="Interior",
            description="",
            owner=self.owner.sheet_data,
            return_location=self.anchor,
            source_key="test:area",
            **kwargs,
        )

    def test_explicit_area_wins_over_anchor(self) -> None:
        override = AreaFactory(name="authored-override")
        room = self._spawn(anchor_room=self.anchor, area=override)
        assert room.room_profile.area_id == override.pk

    def test_anchor_area_inherited_when_no_explicit_area(self) -> None:
        room = self._spawn(anchor_room=self.anchor)
        assert room.room_profile.area_id == self.anchor_area.pk

    def test_no_anchor_and_no_area_means_none(self) -> None:
        room = self._spawn()
        assert room.room_profile.area_id is None


class EntranceTeardownTests(TestCase):
    """complete_instanced_room deletes the temporary doorway."""

    def test_teardown_deletes_entrance_exit(self) -> None:
        anchor = _room("Inn Hallway")
        owner = _pc(anchor)
        room = spawn_instanced_room(
            name="Darkened Interior",
            description="",
            owner=owner.sheet_data,
            return_location=anchor,
            source_key="test:teardown",
            anchor_room=anchor,
        )
        entrance_pk = _entrance_exit(anchor).pk

        complete_instanced_room(room)

        assert not ObjectDB.objects.filter(pk=entrance_pk).exists()
        record = InstancedRoom.objects.filter(room_id=room.pk).first()
        # Ephemeral rooms delete outright; a preserved record must drop the FK.
        assert record is None or record.entrance_exit_id is None

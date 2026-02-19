"""Tests for the instanced rooms system."""

from unittest.mock import MagicMock, PropertyMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.models import RoomProfile
from world.character_sheets.factories import CharacterSheetFactory
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.instances.services import complete_instanced_room, spawn_instanced_room
from world.scenes.factories import SceneFactory


class InstancedRoomModelTests(TestCase):
    """Test InstancedRoom model creation and field defaults."""

    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDB.objects.create(
            db_key="Instance Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.return_room = ObjectDB.objects.create(
            db_key="Town Square",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.sheet = CharacterSheetFactory()
        cls.instance = InstancedRoom.objects.create(
            room=cls.room,
            owner=cls.sheet,
            return_location=cls.return_room,
            source_key="mission.goblin_cave",
        )

    def test_creation_with_all_fields(self):
        """Creating an InstancedRoom with all fields populates them correctly."""
        assert self.instance.room == self.room
        assert self.instance.owner == self.sheet
        assert self.instance.return_location == self.return_room
        assert self.instance.source_key == "mission.goblin_cave"
        assert self.instance.created_at is not None
        assert self.instance.completed_at is None

    def test_status_defaults_to_active(self):
        """Status defaults to ACTIVE when not specified."""
        assert self.instance.status == InstanceStatus.ACTIVE

    def test_str_representation(self):
        """String representation includes room key and status display."""
        expected = "Instance: Instance Room (Active)"
        assert str(self.instance) == expected


class InstancedRoomValidationTests(TestCase):
    """Test InstancedRoom.clean() validation logic."""

    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDB.objects.create(
            db_key="Validation Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.valid_return = ObjectDB.objects.create(
            db_key="Valid Return",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.non_room_obj = ObjectDB.objects.create(
            db_key="A Sword",
            db_typeclass_path="typeclasses.objects.Object",
        )

    def test_return_location_room_typeclass_passes(self):
        """clean() passes when return_location is a Room typeclass."""
        instance = InstancedRoom(room=self.room, return_location=self.valid_return)
        instance.clean()  # should not raise

    def test_return_location_non_room_raises_validation_error(self):
        """clean() raises ValidationError when return_location is not a Room typeclass."""
        instance = InstancedRoom(room=self.room, return_location=self.non_room_obj)
        with self.assertRaises(ValidationError) as ctx:
            instance.clean()
        assert "return_location" in ctx.exception.message_dict

    def test_return_location_null_passes(self):
        """clean() passes when return_location is null."""
        instance = InstancedRoom(room=self.room, return_location=None)
        instance.clean()  # should not raise


class InstancedRoomCascadeTests(TestCase):
    """Test on_delete behavior for InstancedRoom foreign keys."""

    def test_cascade_on_room_delete(self):
        """Deleting the room ObjectDB cascades to delete the InstancedRoom."""
        room = ObjectDB.objects.create(
            db_key="Temp Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        InstancedRoom.objects.create(room=room)
        instance_pk = room.pk

        room.delete()

        assert not InstancedRoom.objects.filter(room_id=instance_pk).exists()

    def test_set_null_on_owner_delete(self):
        """Deleting the CharacterSheet sets owner to null."""
        room = ObjectDB.objects.create(
            db_key="Owner Test Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet = CharacterSheetFactory()
        instance = InstancedRoom.objects.create(room=room, owner=sheet)

        sheet.character.delete()  # CASCADE deletes the CharacterSheet too

        instance.refresh_from_db()
        assert instance.owner is None

    def test_set_null_on_return_location_delete(self):
        """Deleting the return_location ObjectDB sets it to null."""
        room = ObjectDB.objects.create(
            db_key="Return Test Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        return_loc = ObjectDB.objects.create(
            db_key="Return Loc",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        instance = InstancedRoom.objects.create(room=room, return_location=return_loc)

        return_loc.delete()

        instance.refresh_from_db()
        assert instance.return_location is None


class SpawnInstancedRoomTests(TestCase):
    """Test the spawn_instanced_room service function."""

    @classmethod
    def setUpTestData(cls):
        cls.return_room = ObjectDB.objects.create(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.sheet = CharacterSheetFactory()

    def test_spawn_creates_room_and_instance_record(self):
        """spawn_instanced_room creates an ObjectDB room and linked InstancedRoom."""
        room = spawn_instanced_room(
            name="Goblin Cave",
            description="A dank cave.",
            owner=self.sheet,
            return_location=self.return_room,
            source_key="mission.goblin_cave",
        )

        assert room.db_key == "Goblin Cave"
        assert room.db.desc == "A dank cave."

        instance = room.instance_data
        assert instance.owner == self.sheet
        assert instance.return_location == self.return_room
        assert instance.source_key == "mission.goblin_cave"
        assert instance.status == InstanceStatus.ACTIVE
        assert instance.completed_at is None

    def test_spawn_creates_room_profile(self):
        """Spawned room has a RoomProfile auto-created by the Room typeclass."""
        room = spawn_instanced_room(
            name="Profile Test Room",
            description="Testing profile creation.",
            owner=self.sheet,
            return_location=self.return_room,
        )

        assert RoomProfile.objects.filter(objectdb=room).exists()


class CompleteInstancedRoomTests(TestCase):
    """Test the complete_instanced_room service function."""

    @classmethod
    def setUpTestData(cls):
        cls.return_room = ObjectDB.objects.create(
            db_key="Town Square",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.sheet = CharacterSheetFactory()

    def test_complete_deletes_ephemeral_room(self):
        """Completing a room with no scenes deletes both room and InstancedRoom."""
        room = spawn_instanced_room(
            name="Ephemeral Room",
            description="Will be deleted.",
            owner=self.sheet,
            return_location=self.return_room,
        )
        room_pk = room.pk

        complete_instanced_room(room)

        assert not ObjectDB.objects.filter(pk=room_pk).exists()
        assert not InstancedRoom.objects.filter(room_id=room_pk).exists()

    def test_complete_keeps_room_with_scene(self):
        """Completing a room with a Scene preserves both room and InstancedRoom."""
        room = spawn_instanced_room(
            name="Scene Room",
            description="Has a scene.",
            owner=self.sheet,
            return_location=self.return_room,
        )
        SceneFactory(name="Test Scene", location=room)

        complete_instanced_room(room)

        instance = InstancedRoom.objects.get(room=room)
        assert instance.status == InstanceStatus.COMPLETED
        assert instance.completed_at is not None
        assert ObjectDB.objects.filter(pk=room.pk).exists()

    def test_complete_relocates_occupants(self):
        """Completing a room moves puppeted occupants to the return location."""
        room = spawn_instanced_room(
            name="Occupied Room",
            description="Has occupants.",
            owner=self.sheet,
            return_location=self.return_room,
        )
        # Create a scene so the room is preserved (not deleted) after completion,
        # isolating the relocation logic from Evennia's delete-moves-contents behavior.
        SceneFactory(name="Occupant Scene", location=room)

        # Create a mock occupant with an active session
        mock_occupant = MagicMock()
        mock_occupant.sessions.all.return_value = [MagicMock()]

        with patch.object(type(room), "contents", new_callable=PropertyMock) as mock_contents:
            mock_contents.return_value = [mock_occupant]
            complete_instanced_room(room)

        mock_occupant.move_to.assert_called_once_with(self.return_room, quiet=True)

    def test_complete_with_null_return_location(self):
        """Completing a room with null return_location does not crash."""
        room = spawn_instanced_room(
            name="No Return Room",
            description="Nowhere to go back to.",
            owner=self.sheet,
            return_location=None,
        )

        # Should not raise any exception
        complete_instanced_room(room)

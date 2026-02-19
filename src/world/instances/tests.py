"""Tests for the instanced rooms system."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom


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

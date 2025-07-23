from django.test import TestCase
from django.utils.functional import cached_property

from evennia_extensions.factories import ObjectDBFactory
from flows.factories import TriggerFactory


class TriggerRegistryPropertyTests(TestCase):
    def test_registry_bubbles_up_to_room(self):
        room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        char = ObjectDBFactory(
            db_key="bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        self.assertIs(room.trigger_registry, room.trigger_registry)
        self.assertIs(char.trigger_registry, room.trigger_registry)
        self.assertIsInstance(room.__class__.trigger_registry, cached_property)
        self.assertNotIsInstance(char.__class__.trigger_registry, cached_property)

    def test_scene_data_cached_property(self):
        room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )

        self.assertIs(room.scene_data, room.scene_data)
        self.assertIsInstance(room.__class__.scene_data, cached_property)

    def test_triggers_register_and_unregister_on_move(self):
        room1 = ObjectDBFactory(
            db_key="room1",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        room2 = ObjectDBFactory(
            db_key="room2",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char = ObjectDBFactory(
            db_key="bob",
            db_typeclass_path="typeclasses.characters.Character",
        )

        trigger = TriggerFactory(obj=char)

        char.move_to(room1, quiet=True)
        self.assertIn(trigger, room1.trigger_registry.triggers)

        char.move_to(room2, quiet=True)
        self.assertNotIn(trigger, room1.trigger_registry.triggers)
        self.assertIn(trigger, room2.trigger_registry.triggers)

    def test_registry_returns_none_without_location(self):
        char = ObjectDBFactory(
            db_key="wanderer",
            db_typeclass_path="typeclasses.characters.Character",
        )

        self.assertIsNone(char.trigger_registry)

from django.test import TestCase
from django.utils.functional import cached_property

from evennia_extensions.factories import ObjectDBFactory


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

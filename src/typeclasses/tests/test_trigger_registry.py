from functools import cached_property

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.factories import TriggerFactory


class TriggerRegistryPropertyTests(TestCase):
    def test_registry_bubbles_up_to_room(self):
        room = ObjectDBFactory(
            db_key="hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char = ObjectDBFactory(
            db_key="bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        assert room.trigger_registry is room.trigger_registry
        assert char.trigger_registry is room.trigger_registry
        assert isinstance(room.__class__.trigger_registry, cached_property)
        assert not isinstance(char.__class__.trigger_registry, cached_property)

    def test_scene_data_cached_property(self):
        room = ObjectDBFactory(
            db_key="hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        assert room.scene_data is room.scene_data
        assert isinstance(room.__class__.scene_data, cached_property)

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
        assert trigger in room1.trigger_registry.triggers

        char.move_to(room2, quiet=True)
        assert trigger not in room1.trigger_registry.triggers
        assert trigger in room2.trigger_registry.triggers

    def test_registry_returns_none_without_location(self):
        char = ObjectDBFactory(
            db_key="wanderer",
            db_typeclass_path="typeclasses.characters.Character",
        )

        assert char.trigger_registry is None

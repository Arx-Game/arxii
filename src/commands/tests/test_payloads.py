from django.test import TestCase

from commands.payloads import build_examine_payload, build_look_payload
from evennia_extensions.factories import ObjectDBFactory


class PayloadBuilderTests(TestCase):
    """Tests for look and examine payload builders."""

    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="Hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.viewer = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item = ObjectDBFactory(db_key="Rock", location=self.room)
        self.other_char = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        context = self.room.scene_data
        context.initialize_state_for_object(self.viewer)
        context.initialize_state_for_object(self.item)
        context.initialize_state_for_object(self.other_char)
        self.viewer_state = context.get_state_by_pk(self.viewer.pk)
        self.item_state = context.get_state_by_pk(self.item.pk)
        self.other_state = context.get_state_by_pk(self.other_char.pk)

    def test_get_command_included_for_movable_object(self):
        payload = build_look_payload(self.viewer_state, self.item_state)
        actions = [cmd["action"] for cmd in payload["commands"]]
        self.assertIn("get", actions)

    def test_get_command_excluded_for_character(self):
        payload = build_look_payload(self.viewer_state, self.other_state)
        actions = [cmd["action"] for cmd in payload["commands"]]
        self.assertNotIn("get", actions)

    def test_examine_payload_structure(self):
        payload = build_examine_payload(self.viewer_state, self.item_state)
        self.assertIn("description", payload)
        self.assertIn("commands", payload)

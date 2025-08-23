from unittest.mock import MagicMock

from django.test import TestCase

from commands.evennia_overrides.communication import CmdPose, CmdSay, CmdWhisper
from commands.evennia_overrides.perception import CmdInventory
from evennia_extensions.factories import ObjectDBFactory


class CmdInventoryTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="room", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item1 = ObjectDBFactory(db_key="rock", location=self.caller)
        self.item2 = ObjectDBFactory(db_key="scroll", location=self.caller)
        self.caller.msg = MagicMock()

    def test_inventory_lists_items(self):
        cmd = CmdInventory()
        cmd.caller = self.caller
        cmd.args = ""
        cmd.raw_string = "inventory"
        cmd.parse()
        cmd.func()
        sent = cmd.caller.msg.call_args.args[0]
        self.assertIn("rock", sent)
        self.assertIn("scroll", sent)


class CmdSayTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.bystander = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        for obj in (self.room, self.caller, self.bystander):
            self.room.scene_data.initialize_state_for_object(obj)
        self.caller.msg = MagicMock()
        self.bystander.msg = MagicMock()

    def test_say_broadcasts(self):
        cmd = CmdSay()
        cmd.caller = self.caller
        cmd.args = "hello"
        cmd.raw_string = "say hello"
        cmd.parse()
        cmd.func()
        self.assertEqual(
            self.caller.msg.call_args.kwargs["text"][0],
            'You say "hello"',
        )
        self.assertEqual(
            self.bystander.msg.call_args.kwargs["text"][0],
            'Alice says "hello"',
        )


class CmdWhisperTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.caller.search = MagicMock(return_value=self.target)
        self.caller.msg = MagicMock()
        self.target.msg = MagicMock()

    def test_whisper_formats_message(self):
        cmd = CmdWhisper()
        cmd.caller = self.caller
        cmd.args = "Bob=secret"
        cmd.raw_string = "whisper Bob=secret"
        cmd.parse()
        cmd.func()
        self.assertEqual(
            self.target.msg.call_args.args[0],
            'Alice whisper "secret"',
        )
        self.assertEqual(
            self.caller.msg.call_args.args[0],
            'You whisper "secret" to Bob.',
        )

    def test_whisper_exposes_usage_metadata(self):
        cmd = CmdWhisper()
        payload = cmd.to_payload()
        descriptor = payload["descriptors"][0]
        self.assertEqual(descriptor["prompt"], "whisper character=message")
        self.assertEqual(
            descriptor["params_schema"],
            {
                "character": {
                    "type": "string",
                    "widget": "room-character-search",
                    "options_endpoint": "/api/room/characters/",
                },
                "message": {"type": "string"},
            },
        )


class CmdPoseTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.bystander = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        for obj in (self.room, self.caller, self.bystander):
            self.room.scene_data.initialize_state_for_object(obj)
        self.caller.msg = MagicMock()
        self.bystander.msg = MagicMock()

    def test_pose_broadcasts(self):
        cmd = CmdPose()
        cmd.caller = self.caller
        cmd.args = "waves."
        cmd.raw_string = "pose waves."
        cmd.parse()
        cmd.func()
        self.assertEqual(
            self.caller.msg.call_args.kwargs["text"][0],
            "You waves.",
        )
        self.assertEqual(
            self.bystander.msg.call_args.kwargs["text"][0],
            "Alice waves.",
        )

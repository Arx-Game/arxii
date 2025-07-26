from unittest.mock import MagicMock

from django.test import TestCase

from commands.evennia_overrides.movement import CmdDrop, CmdGet, CmdGive, CmdHome
from evennia_extensions.factories import ObjectDBFactory


class CmdGetTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="room", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item = ObjectDBFactory(db_key="rock", location=self.room)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock(return_value=self.item)

    def test_get_item(self):
        cmd = CmdGet()
        cmd.caller = self.caller
        cmd.args = "rock"
        cmd.raw_string = "get rock"
        cmd.parse()
        cmd.func()
        self.item.refresh_from_db()
        self.assertEqual(self.item.location, self.caller)


class CmdDropTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="room", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item = ObjectDBFactory(db_key="rock", location=self.caller)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock(return_value=self.item)

    def test_drop_item(self):
        cmd = CmdDrop()
        cmd.caller = self.caller
        cmd.args = "rock"
        cmd.raw_string = "drop rock"
        cmd.parse()
        cmd.func()
        self.item.refresh_from_db()
        self.assertEqual(self.item.location, self.room)


class CmdGiveTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="room", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.recipient = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.item = ObjectDBFactory(db_key="rock", location=self.caller)
        self.caller.msg = MagicMock()
        # search first for item then for recipient
        self.caller.search = MagicMock(side_effect=[self.item, self.recipient])

    def test_give_item(self):
        cmd = CmdGive()
        cmd.caller = self.caller
        cmd.args = "rock to Bob"
        cmd.raw_string = "give rock to Bob"
        cmd.parse()
        cmd.func()
        self.item.refresh_from_db()
        self.assertEqual(self.item.location, self.recipient)


class CmdHomeTests(TestCase):
    def setUp(self):
        self.home = ObjectDBFactory(
            db_key="Home", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.room = ObjectDBFactory(
            db_key="room", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
            home=self.home,
        )
        self.caller.msg = MagicMock()

    def test_home_moves_caller(self):
        cmd = CmdHome()
        cmd.caller = self.caller
        cmd.args = ""
        cmd.raw_string = "home"
        cmd.parse()
        cmd.func()
        self.caller.refresh_from_db()
        self.assertEqual(self.caller.location, self.home)

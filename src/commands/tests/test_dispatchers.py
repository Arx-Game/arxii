"""Tests for command → action delegation.

These tests verify that commands correctly parse telnet input and
delegate to their action instances.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.items import TakeOutAction
from actions.definitions.movement import GetAction
from actions.types import ActionResult
from commands.evennia_overrides.communication import CmdPose, CmdSay, CmdWhisper
from commands.evennia_overrides.movement import CmdDrop, CmdGet, CmdGive, CmdHome
from commands.evennia_overrides.perception import CmdInventory, CmdLook
from evennia_extensions.factories import ObjectDBFactory


def _make_cmd(cls, caller, args="", obj=None):
    """Create a command instance with caller and args set."""
    cmd = cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd.key} {args}"
    cmd.obj = obj
    cmd.cmdname = cmd.key
    return cmd


class CmdLookTests(TestCase):
    def test_look_at_room(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdLook, caller, args="")
        result = ActionResult(success=True, message="A room")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=room)
        caller.msg.assert_called_with("A room")

    def test_look_at_object(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(db_key="Sword", location=room)
        caller.search = MagicMock(return_value=target)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdLook, caller, args=" Sword")
        result = ActionResult(success=True, message="A sword")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=target)

    def test_look_at_missing_object(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.search = MagicMock(return_value=None)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdLook, caller, args=" missing")
        cmd.func()
        assert caller.msg.call_count >= 1


class CmdInventoryTests(TestCase):
    def test_inventory_delegates_to_action(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdInventory, caller)
        result = ActionResult(success=True, message="You are not carrying anything.")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller)


class CmdSayTests(TestCase):
    def test_say_delegates_text(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdSay, caller, args=" hello")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, text="hello")

    def test_say_empty_text_errors(self):
        caller = ObjectDBFactory(db_key="Alice")
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdSay, caller, args="")
        cmd.func()
        assert caller.msg.call_count >= 1


class CmdPoseTests(TestCase):
    def test_pose_delegates_text(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdPose, caller, args=" stretches.")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, text="stretches.")


class CmdWhisperTests(TestCase):
    def test_whisper_parses_target_and_text(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(db_key="Bob", location=room)
        caller.search = MagicMock(return_value=target)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdWhisper, caller, args=" Bob=secret")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=target, text="secret")


class CmdGetTests(TestCase):
    def test_get_resolves_target(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        item = ObjectDBFactory(db_key="Sword", location=room)
        caller.search = MagicMock(return_value=item)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGet, caller, args=" Sword")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=item)
        # Plain ``get <item>`` should keep using GetAction.
        assert isinstance(cmd.action, GetAction)

    def test_get_from_container_dispatches_take_out(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        chest = ObjectDBFactory(db_key="Chest", location=room)
        ring = ObjectDBFactory(db_key="Ring", location=chest)
        caller.search = MagicMock(side_effect=[chest, ring])
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGet, caller, args=" Ring from Chest")
        # Patch TakeOutAction.run so the test doesn't run the action body.
        with patch.object(
            TakeOutAction,
            "run",
            return_value=ActionResult(success=True),
        ) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=ring)
        assert isinstance(cmd.action, TakeOutAction)
        # Verify search was called for container, then for item-in-container.
        assert caller.search.call_args_list[0].args[0] == "Chest"
        assert caller.search.call_args_list[1].args[0] == "Ring"
        assert caller.search.call_args_list[1].kwargs.get("location") == chest

    def test_take_alias_from_container_dispatches_take_out(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        chest = ObjectDBFactory(db_key="Chest", location=room)
        ring = ObjectDBFactory(db_key="Ring", location=chest)
        caller.search = MagicMock(side_effect=[chest, ring])
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGet, caller, args=" Ring from Chest")
        # The ``take`` alias resolves to the same CmdGet class — verify by
        # forcing cmdname to the alias.
        cmd.cmdname = "take"
        with patch.object(
            TakeOutAction,
            "run",
            return_value=ActionResult(success=True),
        ) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=ring)
        assert isinstance(cmd.action, TakeOutAction)

    def test_get_from_missing_container_errors(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.search = MagicMock(return_value=None)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGet, caller, args=" Ring from Chest")
        cmd.func()
        assert caller.msg.call_count >= 1


class CmdDropTests(TestCase):
    def test_drop_resolves_from_inventory(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        item = ObjectDBFactory(db_key="Sword", location=caller)
        caller.search = MagicMock(return_value=item)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdDrop, caller, args=" Sword")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=item)


class CmdGiveTests(TestCase):
    def test_give_parses_item_and_recipient(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        item = ObjectDBFactory(db_key="Sword", location=caller)
        recipient = ObjectDBFactory(db_key="Bob", location=room)
        caller.search = MagicMock(side_effect=[item, recipient])
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGive, caller, args=" Sword to Bob")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=item, recipient=recipient)


class CmdHomeTests(TestCase):
    def test_home_delegates(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdHome, caller)
        result = ActionResult(success=True, message="You go home.")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller)

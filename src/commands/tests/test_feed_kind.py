"""Commands type the text frames they send, so the web client can sort them (#3856).

A plain ``text`` frame carries no hint of what it is: a look result, "You take the
lantern.", Evennia's "Command 'lok' is not available." and a staff builder's
output all arrived identically and the client could only pile them into one
collapsed strip. The narrative service already types its frames
(``session.msg(text=..., type="gemit")``, ``world/narrative/services.py``) and
the client reads ``kwargs.type``; these tests pin the same contract on the
command layer: a command with a ``feed_kind`` sends its result typed, a
``CommandError`` is typed ``error``, an unmatched command name is typed ``error``
with Evennia's own wording, and a command without a kind sends plain text exactly
as before. Telnet ignores the option, so nothing changes there.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.command import ArxCommand
from commands.currency import CmdDeposit
from commands.evennia_overrides.items import CmdPut, CmdRemove, CmdWear, CmdWithdraw
from commands.evennia_overrides.movement import CmdDrop, CmdGet, CmdGive
from commands.evennia_overrides.perception import CmdLook
from commands.evennia_overrides.system import CmdNoMatch
from commands.exceptions import CommandError
from evennia_extensions.factories import ObjectDBFactory


class _TypedCommand(ArxCommand):
    """A minimal command with a kind, to test the mechanism apart from any verb."""

    key = "typedtest"
    feed_kind = "item"

    def resolve_action_args(self):
        return {}


class _PlainCommand(ArxCommand):
    key = "plaintest"

    def resolve_action_args(self):
        return {}


class _FailingCommand(ArxCommand):
    key = "failtest"

    def _execute(self) -> None:
        msg = "No such thing here."
        raise CommandError(msg)


def _make_cmd(cls, caller, args=""):
    cmd = cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd.key} {args}".strip()
    cmd.cmdname = cmd.key
    return cmd


class FeedKindMechanismTests(TestCase):
    def setUp(self):
        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        self.caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        self.caller.msg = MagicMock()

    def test_a_kinded_command_sends_its_result_typed(self):
        cmd = _make_cmd(_TypedCommand, self.caller)
        cmd.action = MagicMock()
        cmd.action.run.return_value = ActionResult(success=True, message="You take the lantern.")
        cmd.func()
        self.caller.msg.assert_called_once_with("You take the lantern.", type="item")

    def test_a_command_without_a_kind_sends_plain_text(self):
        cmd = _make_cmd(_PlainCommand, self.caller)
        cmd.action = MagicMock()
        cmd.action.run.return_value = ActionResult(success=True, message="Done.")
        cmd.func()
        self.caller.msg.assert_called_once_with("Done.")

    def test_a_command_error_is_typed_error_and_still_sends_the_structured_frame(self):
        cmd = _make_cmd(_FailingCommand, self.caller, args="thing")
        cmd.func()
        self.caller.msg.assert_any_call("No such thing here.", type="error")
        self.caller.msg.assert_any_call(
            command_error={"error": "No such thing here.", "command": "failtest thing"}
        )

    def test_an_empty_result_message_sends_nothing(self):
        cmd = _make_cmd(_TypedCommand, self.caller)
        cmd.action = MagicMock()
        cmd.action.run.return_value = ActionResult(success=True, message="")
        cmd.func()
        self.caller.msg.assert_not_called()


class FeedKindWiringTests(TestCase):
    """The verbs the spec names carry the kinds the client sorts by."""

    def test_look_is_a_look(self):
        assert CmdLook.feed_kind == "look"

    def test_item_handling_verbs_are_items(self):
        for cmd in (CmdGet, CmdDrop, CmdGive, CmdPut, CmdWithdraw, CmdWear, CmdRemove, CmdDeposit):
            assert cmd.feed_kind == "item", cmd.key

    def test_the_base_class_has_no_kind(self):
        assert ArxCommand.feed_kind is None


class CmdNoMatchTests(TestCase):
    """An unmatched command name is a typed error with Evennia's own wording."""

    def setUp(self):
        self.caller = ObjectDBFactory(
            db_key="Alice", db_typeclass_path="typeclasses.characters.Character"
        )
        self.caller.msg = MagicMock()

    def _cmd(self, raw: str) -> CmdNoMatch:
        cmd = CmdNoMatch()
        cmd.caller = self.caller
        # The cmdhandler hands a custom CMD_NOMATCH command the raw input as its
        # args (evennia/commands/cmdhandler.py, "use custom CMD_NOMATCH command").
        cmd.args = raw
        cmd.raw_string = raw
        cmd.cmdset = MagicMock()
        cmd.cmdset.get_all_cmd_keys_and_aliases.return_value = ["look", "say", "pose"]
        return cmd

    def test_close_miss_suggests_the_command_and_is_typed_error(self):
        self._cmd("lok").func()
        self.caller.msg.assert_called_once_with(
            "Command 'lok' is not available. Maybe you meant \"look\"?", type="error"
        )

    def test_nothing_close_points_at_help(self):
        self._cmd("xyzzy").func()
        self.caller.msg.assert_called_once_with(
            "Command 'xyzzy' is not available. Type \"help\" for help.", type="error"
        )

    def test_no_cmdset_still_answers(self):
        cmd = self._cmd("lok")
        cmd.cmdset = None
        cmd.func()
        self.caller.msg.assert_called_once_with(
            "Command 'lok' is not available. Type \"help\" for help.", type="error"
        )

    def test_several_suggestions_join_with_or(self):
        # Evennia quotes each suggestion and joins the last with "or"; the helper
        # is patched so the sentence shape is tested apart from difflib's scoring.
        with patch(
            "commands.evennia_overrides.system.string_suggestions", return_value=["say", "pose"]
        ):
            self._cmd("sey").func()
        self.caller.msg.assert_called_once_with(
            'Command \'sey\' is not available. Maybe you meant "say" or "pose"?', type="error"
        )

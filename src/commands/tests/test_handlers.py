"""Tests for ArxCommand base class error handling."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.perception import LookAction
from actions.types import ActionResult
from commands.command import ArxCommand
from commands.exceptions import CommandError
from evennia_extensions.factories import ObjectDBFactory


class CommandErrorMessageTests(TestCase):
    def test_caller_receives_error_message(self):
        """CommandError should send error text and OOB payload to caller."""
        caller = ObjectDBFactory(db_key="caller")
        caller.msg = MagicMock()

        class FailCmd(ArxCommand):
            key = "fail"
            action = LookAction()

            def resolve_action_args(self):
                msg = "bad"
                raise CommandError(msg)

        cmd = FailCmd()
        cmd.caller = caller
        cmd.args = ""
        cmd.raw_string = "fail"

        cmd.func()
        assert caller.msg.call_count == 2

        text_call = caller.msg.call_args_list[0]
        assert str(text_call.args[0]) == "bad"

        oob_call = caller.msg.call_args_list[1]
        kwargs = oob_call.kwargs
        assert "command_error" in kwargs
        payload = kwargs["command_error"]
        assert payload["error"] == "bad"

    def test_no_action_sends_unavailable_message(self):
        """Command with no action should send unavailable message."""
        caller = ObjectDBFactory(db_key="caller")
        caller.msg = MagicMock()

        cmd = ArxCommand()
        cmd.caller = caller
        cmd.args = ""
        cmd.raw_string = ""
        cmd.key = "stub"

        cmd.func()
        caller.msg.assert_called_once_with("This command is not available.")

    def test_action_result_message_sent_to_caller(self):
        """Successful action result message should be sent to caller."""
        caller = ObjectDBFactory(db_key="caller")
        caller.msg = MagicMock()

        class TestCmd(ArxCommand):
            key = "test"
            action = LookAction()

        cmd = TestCmd()
        cmd.caller = caller
        cmd.args = ""
        cmd.raw_string = ""

        with patch.object(
            cmd.action,
            "run",
            return_value=ActionResult(success=True, message="hello"),
        ):
            cmd.func()
        caller.msg.assert_called_once_with("hello")

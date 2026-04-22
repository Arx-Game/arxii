"""Tests for the @reply command."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.account.prompt_reply import CmdPromptReply
from evennia_extensions.factories import AccountFactory
from flows.execution.prompts import register_pending_prompt


class CmdPromptReplyTests(TestCase):
    """Tests for CmdPromptReply."""

    def setUp(self) -> None:
        self.account = AccountFactory(username="Tester")
        self.caller = MagicMock()

    def _make_cmd(self, args: str) -> CmdPromptReply:
        cmd = CmdPromptReply()
        cmd.account = self.account
        cmd.caller = self.caller
        cmd.args = args
        return cmd

    def test_no_pending_prompt_returns_not_found_message(self) -> None:
        """When no prompt is registered, caller gets an informative message."""
        cmd = self._make_cmd("missing-key yes")
        cmd.func()
        self.caller.msg.assert_called_once_with("No pending prompt with that key.")

    def test_reply_resolves_deferred_and_fires_callback(self) -> None:
        """A valid reply fires the Deferred with the provided answer."""
        deferred = register_pending_prompt(
            account_id=self.account.pk,
            prompt_key="test-key",
            default_answer="no",
        )
        results: list = []
        deferred.addCallback(results.append)

        cmd = self._make_cmd("test-key yes")
        cmd.func()

        self.assertEqual(results, ["yes"])
        self.caller.msg.assert_called_once_with("Reply sent.")

    def test_malformed_input_missing_answer_shows_usage(self) -> None:
        """When only the key is provided (no answer), usage is shown."""
        cmd = self._make_cmd("only-key")
        cmd.func()
        self.caller.msg.assert_called_once_with("Usage: @reply <prompt-key> <answer>")

    def test_empty_args_shows_usage(self) -> None:
        """When args is empty, usage is shown."""
        cmd = self._make_cmd("")
        cmd.func()
        self.caller.msg.assert_called_once_with("Usage: @reply <prompt-key> <answer>")

    def test_answer_with_spaces_is_passed_whole(self) -> None:
        """An answer containing spaces is passed in full (split on first whitespace only)."""
        deferred = register_pending_prompt(
            account_id=self.account.pk,
            prompt_key="spacey-key",
            default_answer="no",
        )
        results: list = []
        deferred.addCallback(results.append)

        cmd = self._make_cmd("spacey-key I want to go north")
        cmd.func()

        self.assertEqual(results, ["I want to go north"])
        self.caller.msg.assert_called_once_with("Reply sent.")

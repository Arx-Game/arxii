"""Tests for CmdIdentify — telnet face of IdentifyAction (#1107 slice 5)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.types import ActionResult
from commands.identification import CmdIdentify
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory


class CmdIdentifyTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="CmdIdentifyRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="cmdidentify_account")
        self.caller = CharacterFactory(db_key="CmdIdentifyAlice", location=self.room)
        self.caller.db_account = account
        self.caller.save()
        self.target = CharacterFactory(db_key="CmdIdentifyBob", location=self.room)

        self.messages: list[str] = []

        def _capture_msg(*a, **kw):
            del kw
            if a:
                self.messages.append(a[0])

        self._capture_msg = _capture_msg

    def _run(self, args: str):
        cmd = CmdIdentify()
        cmd.caller = self.caller
        cmd.args = args
        cmd.raw_string = f"identify {args}"
        cmd.msg = self._capture_msg
        with patch.object(
            CmdIdentify.action.__class__,
            "run",
            return_value=ActionResult(success=True, message="It clicks."),
        ) as mocked:
            cmd.func()
        return mocked

    def test_bare_target_dispatches_with_no_guess(self) -> None:
        mocked = self._run("CmdIdentifyBob")

        mocked.assert_called_once()
        _args, kwargs = mocked.call_args
        self.assertEqual(kwargs.get("actor"), self.caller)
        self.assertEqual(kwargs.get("target"), self.target)
        self.assertNotIn("guess", kwargs)
        self.assertEqual(self.messages, ["It clicks."])

    def test_target_equals_guess_parses_both(self) -> None:
        mocked = self._run("CmdIdentifyBob=Someone Specific")

        mocked.assert_called_once()
        _args, kwargs = mocked.call_args
        self.assertEqual(kwargs.get("target"), self.target)
        self.assertEqual(kwargs.get("guess"), "Someone Specific")

    def test_blank_guess_after_equals_is_omitted(self) -> None:
        mocked = self._run("CmdIdentifyBob=   ")

        mocked.assert_called_once()
        _args, kwargs = mocked.call_args
        self.assertNotIn("guess", kwargs)

    def test_no_args_raises_clean_error_without_dispatching(self) -> None:
        cmd = CmdIdentify()
        cmd.caller = self.caller
        cmd.args = ""
        cmd.raw_string = "identify"
        cmd.msg = self._capture_msg

        with patch.object(CmdIdentify.action.__class__, "run") as mocked:
            cmd.func()

        mocked.assert_not_called()
        self.assertTrue(any("Identify whom" in m for m in self.messages))

    def test_unknown_target_raises_clean_error_without_dispatching(self) -> None:
        cmd = CmdIdentify()
        cmd.caller = self.caller
        cmd.args = "NobodyHereByThisName"
        cmd.raw_string = "identify NobodyHereByThisName"
        cmd.msg = self._capture_msg

        with patch.object(CmdIdentify.action.__class__, "run") as mocked:
            cmd.func()

        mocked.assert_not_called()
        self.assertTrue(self.messages)

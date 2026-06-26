"""Tests for the ``encounter`` GM telnet namespace command (#1494)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.encounter import CmdEncounter


def _make_cmd(caller, args: str) -> CmdEncounter:
    """Build a CmdEncounter with the given caller and args."""
    cmd = CmdEncounter()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"encounter {args}".strip()
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    """Return all positional string messages sent to *caller*.msg."""
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdEncounterRoutingTests(TestCase):
    """Smoke routing and usage surface."""

    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_bare_command_shows_usage(self) -> None:
        """``encounter`` with no subverb prints usage."""
        messages = self._run("")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage message; got {messages}",
        )

    def test_unknown_subverb_shows_usage(self) -> None:
        """An unrecognized subcommand emits a usage hint."""
        messages = self._run("frobnicate")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage message; got {messages}",
        )


class CmdEncounterSubverbTests(TestCase):
    """Each subverb routes to the correct action with the expected kwargs."""

    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    @patch("actions.definitions.gm_combat.BeginEncounterRoundAction.run")
    def test_begin_dispatches_action(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Round begins.")
        messages = self._run("begin")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs.get("name"), None)
        self.assertIn("Round begins.", messages)

    @patch("actions.definitions.gm_combat.ResolveEncounterRoundAction.run")
    def test_resolve_dispatches_action(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(
            success=True,
            message="The round resolves.",
        )
        messages = self._run("resolve")
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs["actor"], self.caller)
        self.assertIn("The round resolves.", messages)

    @patch("actions.definitions.gm_combat.AddOpponentAction.run")
    def test_add_dispatches_name_tier_and_pool(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Opponent added.")
        messages = self._run("add Goblin mook 5")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["name"], "Goblin")
        self.assertEqual(kwargs["tier"], "mook")
        self.assertEqual(kwargs["threat_pool_id"], "5")
        self.assertIn("Opponent added.", messages)

    @patch("actions.definitions.gm_combat.AddOpponentAction.run")
    def test_add_without_pool_passes_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(
            success=False,
            message="Name, tier, and threat pool are required.",
        )
        self._run("add Goblin mook")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["name"], "Goblin")
        self.assertEqual(kwargs["tier"], "mook")
        self.assertIsNone(kwargs.get("threat_pool_id"))

    def test_add_requires_name_and_tier(self) -> None:
        """Missing name/tier emits a usage error."""
        messages = self._run("add")
        self.assertTrue(
            any("Usage" in m or "name" in m.lower() for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_combat.PreviewOpponentDefaultsAction.run")
    def test_default_dispatches_tier(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Preview.")
        messages = self._run("default mook")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["tier"], "mook")
        self.assertIn("Preview.", messages)

    def test_default_requires_tier(self) -> None:
        messages = self._run("default")
        self.assertTrue(
            any("Usage" in m or "tier" in m.lower() for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_combat.AddEncounterParticipantAction.run")
    def test_addpc_dispatches_character_sheet_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="PC added.")
        messages = self._run("addpc Bob")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["character_sheet_id"], "Bob")
        self.assertIn("PC added.", messages)

    def test_addpc_requires_character(self) -> None:
        messages = self._run("addpc")
        self.assertTrue(
            any("Usage" in m or "character" in m.lower() for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_combat.RemoveEncounterParticipantAction.run")
    def test_removepc_dispatches_participant_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="PC removed.")
        messages = self._run("removepc 7")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["participant_id"], "7")
        self.assertIn("PC removed.", messages)

    def test_removepc_requires_participant(self) -> None:
        messages = self._run("removepc")
        self.assertTrue(
            any("Usage" in m or "participant" in m.lower() for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_combat.PauseEncounterAction.run")
    def test_pause_dispatches_action(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Encounter paused.")
        messages = self._run("pause")
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs["actor"], self.caller)
        self.assertIn("Encounter paused.", messages)

    @patch("actions.definitions.gm_combat.EndEncounterAction.run")
    def test_end_dispatches_action(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Encounter ended.")
        messages = self._run("end")
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs["actor"], self.caller)
        self.assertIn("Encounter ended.", messages)


class CmdEncounterPermissionDenialTests(TestCase):
    """Permission-denial results from the action surface to the caller."""

    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    @patch("actions.definitions.gm_combat.BeginEncounterRoundAction.run")
    def test_denial_message_surfaces(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(
            success=False,
            message="Only the scene's GM or staff can do that.",
        )
        cmd = _make_cmd(self.caller, "begin")
        cmd.func()
        messages = _messages(self.caller)
        self.assertIn("Only the scene's GM or staff can do that.", messages)

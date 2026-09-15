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

    @patch("actions.definitions.gm_combat.AddOpponentAction.run")
    def test_add_with_position_token_resolves_position_id(self, mock_run: MagicMock) -> None:
        """#3385: a 4th ``add`` token resolves to a Position pk in the caller's room."""
        from evennia_extensions.factories import ObjectDBFactory
        from world.areas.positioning.constants import PositionKind
        from world.areas.positioning.factories import PositionFactory

        room = ObjectDBFactory(
            db_key="EncounterAddPosRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        throne = PositionFactory(room=room, name="throne", kind=PositionKind.PRIMARY)
        self.caller.location = room
        mock_run.return_value = ActionResult(success=True, message="Opponent added.")

        self._run("add Goblin mook 5 throne")

        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["name"], "Goblin")
        self.assertEqual(kwargs["tier"], "mook")
        self.assertEqual(kwargs["threat_pool_id"], "5")
        self.assertEqual(kwargs["position_id"], throne.pk)

    @patch("actions.definitions.gm_combat.AddOpponentAction.run")
    def test_add_without_position_token_omits_position_id(self, mock_run: MagicMock) -> None:
        """Omitting the position token behaves exactly as today -- no position_id kwarg."""
        mock_run.return_value = ActionResult(success=True, message="Opponent added.")

        self._run("add Goblin mook 5")

        kwargs = mock_run.call_args.kwargs
        self.assertNotIn("position_id", kwargs)

    def test_add_with_unknown_position_token_errors(self) -> None:
        """An unresolvable position name surfaces an error and never calls the action."""
        from evennia_extensions.factories import ObjectDBFactory

        room = ObjectDBFactory(
            db_key="EncounterAddBadPosRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller.location = room

        messages = self._run("add Goblin mook 5 nowhere")

        self.assertTrue(
            any("No such position" in m for m in messages),
            f"Expected a position-not-found error; got {messages}",
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

    @patch("actions.definitions.gm_combat.RemoveOpponentAction.run")
    def test_removenpc_dispatches_opponent_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Opponent removed.")
        messages = self._run("removenpc 9")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["opponent_id"], "9")
        self.assertIn("Opponent removed.", messages)

    def test_removenpc_requires_opponent(self) -> None:
        messages = self._run("removenpc")
        self.assertTrue(
            any("Usage" in m or "opponent" in m.lower() for m in messages),
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

    @patch("actions.definitions.gm_combat.UpdateEncounterSettingsAction.run")
    def test_stakes_dispatches_stakes_level(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Encounter settings updated.")
        messages = self._run("stakes world")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["stakes_level"], "world")
        self.assertIn("Encounter settings updated.", messages)

    def test_stakes_requires_a_level(self) -> None:
        messages = self._run("stakes")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_combat.UpdateEncounterSettingsAction.run")
    def test_risk_dispatches_risk_level(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Encounter settings updated.")
        messages = self._run("risk lethal")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["risk_level"], "lethal")
        self.assertIn("Encounter settings updated.", messages)

    @patch("actions.definitions.gm_combat.UpdateEncounterSettingsAction.run")
    def test_pace_dispatches_pace_mode(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Encounter settings updated.")
        messages = self._run("pace manual")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["pace_mode"], "manual")
        self.assertIn("Encounter settings updated.", messages)

    @patch("actions.definitions.gm_combat.UpdateEncounterSettingsAction.run")
    def test_timer_dispatches_pace_timer_minutes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Encounter settings updated.")
        messages = self._run("timer 20")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["pace_timer_minutes"], "20")
        self.assertIn("Encounter settings updated.", messages)

    def test_timer_requires_a_value(self) -> None:
        messages = self._run("timer")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_combat.UpdateEncounterSettingsAction.run")
    def test_curve_dispatches_curve_name_with_spaces(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Encounter settings updated.")
        messages = self._run("curve Slow Burn")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["escalation_curve"], "Slow Burn")
        self.assertIn("Encounter settings updated.", messages)

    def test_curve_requires_an_argument(self) -> None:
        messages = self._run("curve")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage error; got {messages}",
        )


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

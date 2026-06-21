"""Unit tests for CmdDeclareTechnique (thin telnet shell over the COMBAT dispatcher)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from commands.combat import CmdDeclareTechnique
from commands.exceptions import CommandError


def _make_cmd(args):
    cmd = CmdDeclareTechnique()
    cmd.caller = MagicMock()
    cmd.args = args
    cmd.raw_string = f"cast {args}"
    cmd.cmdname = "cast"
    return cmd


class CmdDeclareTechniqueTests(TestCase):
    def test_builds_combat_ref_for_known_technique(self) -> None:
        cmd = _make_cmd("Firebolt at Mook")
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=42) as mt,
            patch.object(cmd, "_resolve_opponent_target_id", return_value=7),
        ):
            ref = cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        mt.assert_called_once()
        self.assertEqual(ref.backend, ActionBackend.COMBAT)
        self.assertEqual(ref.technique_id, 42)
        self.assertEqual(kwargs["focused_opponent_target_id"], 7)
        self.assertEqual(kwargs["effort_level"], "medium")

    def test_blank_args_raises(self) -> None:
        cmd = _make_cmd("")
        with self.assertRaises(CommandError):
            cmd.resolve_action_ref()

    def test_effort_override_parsed(self) -> None:
        cmd = _make_cmd("Firebolt at Mook effort=high")
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_resolve_opponent_target_id", return_value=2),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["effort_level"], "high")

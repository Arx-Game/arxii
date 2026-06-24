"""Unit tests for CmdDeclareTechnique (scene-adaptive telnet shell).

These tests verify the command's parsing and ref/kwargs construction without
touching the full dispatch pipeline.  The command now emits SCENE_ADAPTIVE
refs (not COMBAT); target resolution branches on whether the caller is in a
DECLARING combat encounter.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from commands.combat import CmdDeclareTechnique
from commands.exceptions import CommandError
from world.magic.models.techniques import ConditionTargetKind

_DERIVE = "world.magic.services.targeting.derive_target_relationship"


def _make_cmd(args):
    cmd = CmdDeclareTechnique()
    cmd.caller = MagicMock()
    cmd.args = args
    cmd.raw_string = f"cast {args}"
    cmd.cmdname = "cast"
    return cmd


class CmdDeclareTechniqueTests(TestCase):
    def test_builds_scene_adaptive_ref_for_known_technique(self) -> None:
        """resolve_action_ref returns a SCENE_ADAPTIVE ref with the technique id."""
        cmd = _make_cmd("Firebolt")
        with patch.object(cmd, "_resolve_technique_id", return_value=42) as mt:
            ref = cmd.resolve_action_ref()
        mt.assert_called_once()
        self.assertEqual(ref.backend, ActionBackend.SCENE_ADAPTIVE)
        self.assertEqual(ref.registry_key, "cast_technique")
        self.assertEqual(ref.technique_id, 42)

    def test_blank_args_raises(self) -> None:
        cmd = _make_cmd("")
        with self.assertRaises(CommandError):
            cmd.resolve_action_ref()

    def test_combat_path_hostile_technique_adds_focused_opponent_target_id(self) -> None:
        """In combat, a hostile (ENEMY) technique resolves the target to a CombatOpponent."""
        cmd = _make_cmd("Firebolt at Mook effort=high")
        participant = MagicMock()
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_resolve_technique", return_value=MagicMock()),
            patch.object(cmd, "_combat_participant_or_none", return_value=participant),
            patch.object(cmd, "_resolve_opponent_target_id", return_value=7),
            patch(_DERIVE, return_value=ConditionTargetKind.ENEMY),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["effort_level"], "high")
        self.assertEqual(kwargs["focused_opponent_target_id"], 7)
        self.assertNotIn("focused_ally_target_id", kwargs)
        self.assertNotIn("target_persona_id", kwargs)

    def test_combat_path_beneficial_technique_adds_focused_ally_target_id(self) -> None:
        """In combat, a beneficial (ALLY) technique resolves the target to a CombatParticipant."""
        cmd = _make_cmd("Mend at Aria")
        participant = MagicMock()
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_resolve_technique", return_value=MagicMock()),
            patch.object(cmd, "_combat_participant_or_none", return_value=participant),
            patch.object(cmd, "_resolve_ally_target_id", return_value=5),
            patch(_DERIVE, return_value=ConditionTargetKind.ALLY),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["focused_ally_target_id"], 5)
        self.assertNotIn("focused_opponent_target_id", kwargs)
        self.assertNotIn("target_persona_id", kwargs)

    def test_noncombat_path_adds_target_persona_id(self) -> None:
        """Outside combat the target resolves to a Persona."""
        cmd = _make_cmd("Firebolt at Aria")
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
            patch.object(cmd, "_resolve_target_persona_id", return_value=99),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["target_persona_id"], 99)
        self.assertNotIn("focused_opponent_target_id", kwargs)

    def test_mixed_case_effort_parsed(self) -> None:
        """Mixed-case 'Effort=HIGH' must not raise IndexError and must parse correctly."""
        cmd = _make_cmd("Firebolt Effort=HIGH")
        with patch.object(cmd, "_resolve_technique_id", return_value=1):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["effort_level"], "high")

    def test_no_target_returns_only_effort_level(self) -> None:
        """When no 'at <target>' is given, only effort_level is in the kwargs."""
        cmd = _make_cmd("Firebolt")
        with patch.object(cmd, "_resolve_technique_id", return_value=1):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs, {"effort_level": "medium"})

    def test_ambiguous_opponent_name_raises(self) -> None:
        """Two opponents with the same name must raise CommandError (combat path)."""
        cmd = _make_cmd("Firebolt at Mook")
        opp1 = MagicMock()
        opp1.pk = 1
        opp2 = MagicMock()
        opp2.pk = 2

        participant = MagicMock()
        participant.encounter = MagicMock()

        with (
            patch.object(cmd, "_resolve_technique_id", return_value=99),
            patch.object(cmd, "_resolve_technique", return_value=MagicMock()),
            patch.object(cmd, "_combat_participant_or_none", return_value=participant),
            patch(_DERIVE, return_value=ConditionTargetKind.ENEMY),
            patch("world.combat.models.CombatOpponent") as MockOpponent,
        ):
            MockOpponent.objects.filter.return_value = [opp1, opp2]
            cmd.resolve_action_ref()
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()


class CmdsetRegistrationTests(TestCase):
    def test_cast_command_registered(self) -> None:
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("cast", keys)

    def test_attempt_command_not_registered(self) -> None:
        """CmdAttempt was removed; 'attempt' must no longer appear in the cmdset."""
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertNotIn("attempt", keys)

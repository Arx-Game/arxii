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
from world.magic.factories import CharacterResonanceFactory, ThreadFactory
from world.magic.models.techniques import ConditionTargetKind
from world.magic.types.pull import CastPullDeclaration

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


class CmdDeclareTechniquePullParseTests(TestCase):
    """Tests for pull=/resonance=/tier= parsing and resolution in CmdDeclareTechnique (#1455).

    Uses setUpTestData for ORM objects (Thread, Resonance) since these are
    plain Django models with no Evennia ObjectDB dependency.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.cr = CharacterResonanceFactory(balance=50)
        cls.sheet = cls.cr.character_sheet
        cls.resonance = cls.cr.resonance
        cls.thread = ThreadFactory(owner=cls.sheet, resonance=cls.resonance, name="Ember Strand")

    def _make_cmd(self, args: str) -> CmdDeclareTechnique:
        cmd = CmdDeclareTechnique()
        cmd.caller = MagicMock()
        cmd.caller.sheet_data = self.sheet
        cmd.args = args
        cmd.raw_string = f"cast {args}"
        cmd.cmdname = "cast"
        return cmd

    # -------------------------------------------------------------------------
    # Parsing tests (no ORM resolution — just verify cached state after _parse_args)
    # -------------------------------------------------------------------------

    def test_pull_keyword_parsed_into_state(self) -> None:
        """_parse_args caches pull thread string and resonance string."""
        cmd = self._make_cmd(f"Firebolt pull={self.thread.name} resonance={self.resonance.name}")
        with patch.object(cmd, "_resolve_technique_id", return_value=1):
            cmd.resolve_action_ref()
        self.assertEqual(cmd._pull_thread_str, self.thread.name)
        self.assertEqual(cmd._pull_resonance_str, self.resonance.name)
        self.assertEqual(cmd._pull_tier, 1)

    def test_tier_keyword_parsed_correctly(self) -> None:
        """tier=2 is stored on the command after _parse_args."""
        cmd = self._make_cmd(
            f"Firebolt pull={self.thread.name} resonance={self.resonance.name} tier=2"
        )
        with patch.object(cmd, "_resolve_technique_id", return_value=1):
            cmd.resolve_action_ref()
        self.assertEqual(cmd._pull_tier, 2)

    def test_invalid_tier_raises(self) -> None:
        """tier=5 must raise CommandError."""
        cmd = self._make_cmd(
            f"Firebolt pull={self.thread.name} resonance={self.resonance.name} tier=5"
        )
        with patch.object(cmd, "_resolve_technique_id", return_value=1):
            with self.assertRaises(CommandError):
                cmd.resolve_action_ref()

    def test_pull_without_resonance_raises(self) -> None:
        """pull= without resonance= must raise CommandError."""
        cmd = self._make_cmd(f"Firebolt pull={self.thread.name}")
        with patch.object(cmd, "_resolve_technique_id", return_value=1):
            with self.assertRaises(CommandError):
                cmd.resolve_action_ref()

    def test_no_pull_leaves_state_none(self) -> None:
        """Without pull= the command caches _pull_thread_str as None."""
        cmd = self._make_cmd("Firebolt")
        with patch.object(cmd, "_resolve_technique_id", return_value=1):
            cmd.resolve_action_ref()
        self.assertIsNone(cmd._pull_thread_str)

    # -------------------------------------------------------------------------
    # Resolution tests — verify resolve_action_args produces cast_pull kwarg
    # -------------------------------------------------------------------------

    def test_resolve_action_args_includes_cast_pull(self) -> None:
        """resolve_action_args includes cast_pull=CastPullDeclaration when pull= is given."""
        cmd = self._make_cmd(
            f"Firebolt pull={self.thread.name} resonance={self.resonance.name} tier=1"
        )
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertIn("cast_pull", kwargs)
        pull = kwargs["cast_pull"]
        self.assertIsInstance(pull, CastPullDeclaration)
        self.assertEqual(pull.resonance, self.resonance)
        self.assertEqual(pull.tier, 1)
        self.assertIn(self.thread, pull.threads)

    def test_resolve_action_args_no_pull_key_when_absent(self) -> None:
        """resolve_action_args omits cast_pull when no pull= was given."""
        cmd = self._make_cmd("Firebolt")
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertNotIn("cast_pull", kwargs)

    def test_unknown_resonance_raises(self) -> None:
        """pull= with an unknown resonance name raises CommandError."""
        cmd = self._make_cmd(f"Firebolt pull={self.thread.name} resonance=NoSuchResonanceXXX")
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
        ):
            cmd.resolve_action_ref()
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_unknown_thread_raises(self) -> None:
        """pull= with a thread name that doesn't exist for the caster raises CommandError."""
        cmd = self._make_cmd(f"Firebolt pull=NoSuchThreadXXX resonance={self.resonance.name}")
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
        ):
            cmd.resolve_action_ref()
            with self.assertRaises(CommandError):
                cmd.resolve_action_args()

    def test_pull_keywords_order_independent(self) -> None:
        """resonance= tier= pull= in any order resolves correctly."""
        cmd = self._make_cmd(
            f"Firebolt resonance={self.resonance.name} tier=2 pull={self.thread.name}"
        )
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertIn("cast_pull", kwargs)
        self.assertEqual(kwargs["cast_pull"].tier, 2)

    def test_pull_coexists_with_effort_and_target(self) -> None:
        """pull= coexists with effort= and at <target> without interfering."""
        cmd = self._make_cmd(
            f"Firebolt at Aria pull={self.thread.name} resonance={self.resonance.name} effort=high"
        )
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
            patch.object(cmd, "_resolve_target_persona_id", return_value=99),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["effort_level"], "high")
        self.assertEqual(kwargs.get("target_persona_id"), 99)
        self.assertIn("cast_pull", kwargs)

    def test_pull_effort_order_independent_effort_between_pull_and_resonance(self) -> None:
        """effort= between pull= and resonance= must not drop resonance= (#1455).

        Previously _parse_args split on effort= first, discarding everything after it
        (including resonance=).  This test was RED before the fix (CommandError:
        pull= requires resonance=) and GREEN after.
        """
        # effort= sits between pull= and resonance=
        cmd = self._make_cmd(
            f"Firebolt pull={self.thread.name} effort=high resonance={self.resonance.name}"
        )
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["effort_level"], "high")
        self.assertIn("cast_pull", kwargs)
        pull: CastPullDeclaration = kwargs["cast_pull"]
        self.assertEqual(pull.resonance, self.resonance)
        self.assertEqual(pull.threads[0], self.thread)

    def test_pull_effort_order_independent_effort_before_pull(self) -> None:
        """effort= before pull= and resonance= must resolve correctly (#1455)."""
        cmd = self._make_cmd(
            f"Firebolt effort=high pull={self.thread.name} resonance={self.resonance.name}"
        )
        with (
            patch.object(cmd, "_resolve_technique_id", return_value=1),
            patch.object(cmd, "_combat_participant_or_none", return_value=None),
        ):
            cmd.resolve_action_ref()
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["effort_level"], "high")
        self.assertIn("cast_pull", kwargs)
        pull: CastPullDeclaration = kwargs["cast_pull"]
        self.assertEqual(pull.resonance, self.resonance)
        self.assertEqual(pull.threads[0], self.thread)


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

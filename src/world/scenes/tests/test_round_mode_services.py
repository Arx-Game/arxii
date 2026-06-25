"""Tests for set_scene_round_mode and RoundModeError."""

from django.test import TestCase

from world.scenes.constants import RoundStatus, SceneRoundMode, SceneRoundStartReason
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.models import SceneActionDeclaration
from world.scenes.round_services import RoundModeError, set_scene_round_mode


class SetSceneRoundModeTests(TestCase):
    def test_into_strict_is_allowed_live(self):
        """Switching an OPEN/POSE_ORDER round to STRICT is always allowed."""
        rnd = SceneRoundFactory(mode=SceneRoundMode.POSE_ORDER)
        result = set_scene_round_mode(rnd, mode=SceneRoundMode.STRICT)
        rnd.refresh_from_db()
        self.assertEqual(rnd.mode, SceneRoundMode.STRICT)
        self.assertIs(result, rnd)

    def test_change_knobs_only_allowed(self):
        """Changing quorum/cap/lock with mode=None never triggers either guard."""
        rnd = SceneRoundFactory(
            mode=SceneRoundMode.STRICT,
            advance_quorum_pct=60,
            max_actions_per_round=1,
            per_target_repeat_lock=False,
        )
        result = set_scene_round_mode(
            rnd,
            advance_quorum_pct=80,
            max_actions_per_round=2,
            per_target_repeat_lock=True,
        )
        rnd.refresh_from_db()
        self.assertEqual(rnd.advance_quorum_pct, 80)
        self.assertEqual(rnd.max_actions_per_round, 2)
        self.assertTrue(rnd.per_target_repeat_lock)
        # mode unchanged
        self.assertEqual(rnd.mode, SceneRoundMode.STRICT)
        self.assertIs(result, rnd)

    def test_out_of_strict_with_pending_declaration_raises(self):
        """Switching away from STRICT while a pending non-immediate declaration exists raises."""
        rnd = SceneRoundFactory(mode=SceneRoundMode.STRICT)
        participant = SceneRoundParticipantFactory(scene_round=rnd)
        # Create a pending non-immediate declaration (deferred STRICT ledger row).
        SceneActionDeclaration.objects.create(
            scene_round=rnd,
            round_number=rnd.round_number,
            participant=participant,
            is_immediate=False,
            is_pass=False,
        )
        with self.assertRaises(RoundModeError):
            set_scene_round_mode(rnd, mode=SceneRoundMode.POSE_ORDER)

    def test_out_of_strict_without_pending_is_allowed(self):
        """Switching away from STRICT with NO pending declarations is permitted."""
        rnd = SceneRoundFactory(mode=SceneRoundMode.STRICT)
        result = set_scene_round_mode(rnd, mode=SceneRoundMode.OPEN)
        rnd.refresh_from_db()
        self.assertEqual(rnd.mode, SceneRoundMode.OPEN)
        self.assertIs(result, rnd)

    def test_danger_round_knob_change_allowed(self):
        """#1466: a danger round is an ordinary STRICT round; there is no DANGER-specific
        block. Knob changes apply like any other round (no pending declarations)."""
        rnd = SceneRoundFactory(
            start_reason=SceneRoundStartReason.DANGER, mode=SceneRoundMode.STRICT
        )
        set_scene_round_mode(rnd, advance_quorum_pct=50)
        rnd.refresh_from_db()
        self.assertEqual(rnd.advance_quorum_pct, 50)

    def test_danger_round_leaving_strict_with_pending_still_guarded(self):
        """The out-of-STRICT guard still applies to a danger round with pending deferreds."""
        from world.character_sheets.factories import CharacterSheetFactory

        rnd = SceneRoundFactory(
            start_reason=SceneRoundStartReason.DANGER,
            status=RoundStatus.DECLARING,
            round_number=1,
            mode=SceneRoundMode.STRICT,
        )
        participant = SceneRoundParticipantFactory(
            scene_round=rnd, character_sheet=CharacterSheetFactory()
        )
        SceneActionDeclaration.objects.create(
            scene_round=rnd,
            round_number=1,
            participant=participant,
            is_immediate=False,
            is_pass=True,
        )
        with self.assertRaises(RoundModeError):
            set_scene_round_mode(rnd, mode=SceneRoundMode.POSE_ORDER)

    def test_only_changed_fields_saved(self):
        """save(update_fields=...) is called with only the supplied fields (no extra writes)."""
        rnd = SceneRoundFactory(
            mode=SceneRoundMode.POSE_ORDER,
            advance_quorum_pct=60,
            max_actions_per_round=1,
            per_target_repeat_lock=False,
        )
        set_scene_round_mode(rnd, advance_quorum_pct=75)
        rnd.refresh_from_db()
        # Only advance_quorum_pct changed; others untouched.
        self.assertEqual(rnd.advance_quorum_pct, 75)
        self.assertEqual(rnd.mode, SceneRoundMode.POSE_ORDER)
        self.assertEqual(rnd.max_actions_per_round, 1)
        self.assertFalse(rnd.per_target_repeat_lock)

    def test_immediate_only_declarations_do_not_block_out_of_strict(self):
        """Only is_immediate=False rows trigger the out-of-STRICT guard; immediate rows don't."""
        rnd = SceneRoundFactory(mode=SceneRoundMode.STRICT)
        participant = SceneRoundParticipantFactory(scene_round=rnd)
        # An immediate row (POSE_ORDER/OPEN resolved action) — must NOT block.
        SceneActionDeclaration.objects.create(
            scene_round=rnd,
            round_number=rnd.round_number,
            participant=participant,
            is_immediate=True,
            is_pass=False,
        )
        result = set_scene_round_mode(rnd, mode=SceneRoundMode.POSE_ORDER)
        rnd.refresh_from_db()
        self.assertEqual(rnd.mode, SceneRoundMode.POSE_ORDER)
        self.assertIs(result, rnd)

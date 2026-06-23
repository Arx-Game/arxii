"""Pose-order round policy tests: is_repeat_blocked, record_pose_order_action, advance quorum."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus, SceneRoundMode
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory


class PoseOrderTests(TestCase):
    """POSE_ORDER round: is_repeat_blocked semantics + quorum advance."""

    def setUp(self):
        from world.scenes.round_services import (
            advance_pose_order_round_if_quorum,
            record_pose_order_action,
        )

        self.record = record_pose_order_action
        self.advance = advance_pose_order_round_if_quorum

    def _make_round(self, *, quorum_pct=60, cap=1, lock=False):
        """POSE_ORDER DECLARING round with 3 active participants."""
        rnd = SceneRoundFactory(
            mode=SceneRoundMode.POSE_ORDER,
            status=RoundStatus.DECLARING,
            round_number=1,
            advance_quorum_pct=quorum_pct,
            max_actions_per_round=cap,
            per_target_repeat_lock=lock,
        )
        pa = SceneRoundParticipantFactory(scene_round=rnd, character_sheet=CharacterSheetFactory())
        pb = SceneRoundParticipantFactory(scene_round=rnd, character_sheet=CharacterSheetFactory())
        pc = SceneRoundParticipantFactory(scene_round=rnd, character_sheet=CharacterSheetFactory())
        return rnd, pa, pb, pc

    def test_blocked_after_acting_until_quorum(self):
        """A acts -> blocked; B acts -> quorum met -> A unblocked."""
        from world.scenes.round_context import SceneRoundContext

        rnd, pa, pb, _pc = self._make_round(quorum_pct=60, cap=1)
        # quorum = ceil(0.6 * 3) = 2

        ctx_a = SceneRoundContext(rnd)
        # Before A acts: not blocked
        self.assertFalse(ctx_a.is_repeat_blocked(pa.character_sheet, None, None))

        # A acts
        self.record(rnd, pa, None)
        rnd.refresh_from_db()
        # A is now blocked (used cap=1)
        self.assertTrue(ctx_a.is_repeat_blocked(pa.character_sheet, None, None))

        # Quorum not met yet (1 actor, need 2)
        result = self.advance(rnd)
        result.refresh_from_db()
        self.assertEqual(result.round_number, 1)  # round did NOT advance

        # B acts
        self.record(rnd, pb, None)
        result = self.advance(rnd)
        result.refresh_from_db()
        # Now 2 distinct actors >= ceil(0.6 * 3) = 2 -> round advances
        self.assertEqual(result.round_number, 2)
        # A is no longer blocked (new round_number)
        self.assertFalse(ctx_a.is_repeat_blocked(pa.character_sheet, None, None))

    def test_cap_two_allows_second_action(self):
        """cap=2: A acts once -> not blocked; twice -> blocked."""
        from world.scenes.round_context import SceneRoundContext

        rnd, pa, _pb, _pc = self._make_round(cap=2)
        ctx_a = SceneRoundContext(rnd)

        # A acts once: not yet blocked (1 < 2)
        self.record(rnd, pa, None)
        self.assertFalse(ctx_a.is_repeat_blocked(pa.character_sheet, None, None))

        # A acts again: now blocked (2 >= 2)
        self.record(rnd, pa, None)
        self.assertTrue(ctx_a.is_repeat_blocked(pa.character_sheet, None, None))

    def test_per_target_lock(self):
        """per_target_repeat_lock=True: A acted at B -> blocked vs B; not blocked vs C."""
        from world.scenes.factories import PersonaFactory
        from world.scenes.round_context import SceneRoundContext

        rnd, pa, pb, pc = self._make_round(lock=True, cap=2)
        # Use cap=2 so the row count alone doesn't block A; only the per-target lock triggers.
        ctx_a = SceneRoundContext(rnd)

        persona_b = PersonaFactory(character_sheet=pb.character_sheet)
        persona_c = PersonaFactory(character_sheet=pc.character_sheet)

        # A acts targeting B's persona
        self.record(rnd, pa, persona_b)
        # Blocked vs B (already targeted)
        self.assertTrue(ctx_a.is_repeat_blocked(pa.character_sheet, None, persona_b))
        # Not blocked vs C (not yet targeted)
        self.assertFalse(ctx_a.is_repeat_blocked(pa.character_sheet, None, persona_c))
        # Not blocked vs None (no target)
        self.assertFalse(ctx_a.is_repeat_blocked(pa.character_sheet, None, None))

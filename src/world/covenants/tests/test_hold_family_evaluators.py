"""Tests for hold-family + mark situation evaluators (#2664)."""

from django.test import TestCase

from world.covenants.perks.context import SituationContext, SituationParams
from world.covenants.perks.evaluators import SITUATION_EVALUATORS


class HoldFamilyEvaluatorFalsePathTest(TestCase):
    """Every hold-family evaluator returns False when required context is missing.

    These are the cheap, fast, universally-applicable False-path tests.
    True-path tests require full combat + covenant setup and are exercised
    via the integration test suite.
    """

    def _ctx(self, **overrides):
        defaults = {
            "holder": None,
            "subject": None,
            "target": None,
            "resolution": None,
        }
        defaults.update(overrides)
        return SituationContext(**defaults)

    def test_enemy_held_by_ally_no_context(self):
        result = SITUATION_EVALUATORS["enemy_held_by_ally"](self._ctx(), SituationParams())
        self.assertFalse(result)

    def test_barrier_contested_no_context(self):
        result = SITUATION_EVALUATORS["barrier_contested"](self._ctx(), SituationParams())
        self.assertFalse(result)

    def test_shielded_by_ally_no_target(self):
        result = SITUATION_EVALUATORS["shielded_by_ally"](self._ctx(), SituationParams())
        self.assertFalse(result)

    def test_target_is_marked_by_ally_no_context(self):
        result = SITUATION_EVALUATORS["target_is_marked_by_ally"](self._ctx(), SituationParams())
        self.assertFalse(result)

    def test_shielded_by_ally_no_shielded_template(self):
        """When the Shielded ConditionTemplate doesn't exist, returns False."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.perks.context import SituationContext

        sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        ctx = SituationContext(
            holder=sheet,
            subject=sheet,
            target=target_sheet,
            resolution=None,
        )
        # Shielded template may or may not exist in test DB; either way the
        # evaluator must not crash and must return False when no condition
        # instance exists on the target.
        result = SITUATION_EVALUATORS["shielded_by_ally"](ctx, SituationParams())
        self.assertFalse(result)

    def test_all_evaluators_registered(self):
        """All four new situations have registered evaluators."""
        for situation in (
            "enemy_held_by_ally",
            "barrier_contested",
            "shielded_by_ally",
            "target_is_marked_by_ally",
        ):
            self.assertIn(situation, SITUATION_EVALUATORS, f"{situation} not registered")

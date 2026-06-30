"""Affection-derived social difficulty + relative shifts (#1697)."""

from types import SimpleNamespace

from django.test import TestCase

from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.social_difficulty import resolved_base_difficulty


def _request(*, category, tier_modifier=0):
    """A minimal SceneActionRequest stand-in for the difficulty helper (it reads template only)."""
    template = SimpleNamespace(category=category, difficulty_tier_modifier=tier_modifier)
    return SimpleNamespace(action_template=template, initiator_persona=None)


class ResolvedBaseDifficultyTests(TestCase):
    def test_non_social_uses_absolute_choice(self) -> None:
        req = _request(category="magic")
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.HARD, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.HARD])

    def test_social_neutral_no_target_is_normal(self) -> None:
        # No target_sheet → affection 0 (neutral); defender NORMAL → no shift → Normal.
        req = _request(category="social")
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.NORMAL, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.NORMAL])

    def test_defender_hard_shifts_one_tier_above_the_derived_base(self) -> None:
        # Neutral base (Normal) + defender HARD (+1 tier relative to Normal) → Hard.
        req = _request(category="social")
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.HARD, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.HARD])

    def test_seduce_tier_modifier_adds_a_tier(self) -> None:
        # Neutral base (Normal) + defender NORMAL (no shift) + Seduce (+1 tier) → Hard.
        req = _request(category="social", tier_modifier=1)
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.NORMAL, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.HARD])

    def test_clamps_at_the_top_tier(self) -> None:
        # Defender DAUNTING (+2) + Seduce (+1) from Normal base → clamps at Harrowing (top).
        req = _request(category="social", tier_modifier=1)
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.DAUNTING, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.HARROWING])

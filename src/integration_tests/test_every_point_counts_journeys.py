"""Journeys for the slide, and big buffs lifting a check off an impossible chart (#4601, #4723).

Ysmay, a level-1 character, checks through the real check pipeline
(``perform_check_with_modifiers``, which gathers her conditions), with the
seeded rank ladder and result charts. Rank N starts at 18 + 8 x (N - 1) points (a level is 8
points wide), rank 0 is below 18. Her own total is 5 points: Incompetent (rank 0), 28% toward
Novice (rank 1), because 5 of the 18 points of rank 0's band. Buffs are real conditions on
her with check modifiers. The returned chart exposes the exact odds, without estimating them
from repeated rolls.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from integration_tests.harness import JourneyCase
from world.checks.constants import ModifierLane, ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.checks.modifier_models import ModifierTaper
from world.checks.services import perform_check_with_modifiers, preview_check_difficulty
from world.checks.slide import resolve_standing
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.services import difficulty_indicator_for_rank_difference
from world.seeds.checks import seed_check_resolution_tables
from world.traits.models import ResultChart

NOVICE = 18  # Novice (rank 1), 0% through its band
COMPETENT = 34  # Competent (rank 3)
RANK_EIGHT = 74  # 18 + 8 x 7
RANK_THIRTEEN = 114  # 18 + 8 x 12
RANK_TWENTY = 170  # 18 + 8 x 19


class EveryPointCounts(JourneyCase):
    """A check's odds slide with every point, and enough buffs make the impossible possible."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        ResultChart.clear_cache()
        self.climbing = CheckTypeFactory(name="Climbing", description="Scale a wall or a cliff.")
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)

    def buff(self, value: int, name: str) -> None:
        """A condition on Ysmay that adds ``value`` to her Climbing checks."""
        condition = ConditionTemplateFactory(name=name)
        ConditionCheckModifierFactory(
            condition=condition,
            check_type=self.climbing,
            check_category=None,
            modifier_value=value,
        )
        ConditionInstanceFactory(target=self.ysmay, condition=condition)

    def success_odds(self, difficulty: int) -> float:
        """Get the exact odds returned by the real check with Ysmay's conditions."""
        result = perform_check_with_modifiers(
            self.ysmay, self.climbing, target_difficulty=difficulty
        )
        return result.standing.slid.at_least(1)

    def test_her_result_says_where_she_stood(self) -> None:
        result = perform_check_with_modifiers(self.ysmay, self.climbing, target_difficulty=NOVICE)
        self.assertEqual(result.total_points, 5)
        self.assertEqual(
            result.standing_text,
            "Incompetent (rank 0), 28% toward Novice (rank 1) against Novice (rank 1)",
        )
        self.assertEqual(result.rank_difference, -1)

        # Rolled at the table, her own message carries it; the room's narration does not.
        self.telnet(self.ysmay, "scene start")
        told = self.telnet(self.ysmay, "check Climbing at trivial")
        self.assertIn(
            "Your standing: Incompetent (rank 0), 28% toward Novice (rank 1) against "
            "Incompetent (rank 0), 83% toward Novice (rank 1).",
            told,
        )

    def test_halfway_through_a_band_she_gets_the_halfway_odds(self) -> None:
        # Chart -1 (22% Success or better) slid 5/18 of the way toward chart 0 (40% once its
        # Critical Success counts as Success): 22% + 5/18 x 18% = 27%. Whole ranks give 22%.
        result = perform_check_with_modifiers(self.ysmay, self.climbing, target_difficulty=NOVICE)
        self.assertAlmostEqual(result.standing.slid.at_least(1), 0.27)
        self.assertEqual(result.standing.slid.at_least(2), 0)

    def test_rolls_on_either_side_of_the_success_boundary(self) -> None:
        # 27% success puts the boundary at 73. Positions are face minus fraction.
        for face, fraction, expected_success in ((73, 0.01, False), (74, 0.99, True)):
            with (
                self.subTest(face=face, fraction=fraction),
                patch("world.checks.services.random.randint", return_value=face),
                patch("world.checks.services.random.random", return_value=fraction),
            ):
                result = perform_check_with_modifiers(
                    self.ysmay, self.climbing, target_difficulty=NOVICE
                )
                self.assertEqual(result.success_level >= 1, expected_success)

    def test_one_small_buff_moves_the_odds(self) -> None:
        plain = self.success_odds(NOVICE)
        # +3 keeps her in Incompetent (rank 0); whole ranks would ignore it.
        self.buff(3, "A word of encouragement")
        buffed = self.success_odds(NOVICE)
        # 8 of the 18 points of the band: 22% + 8/18 x 18% = 30%.
        self.assertAlmostEqual(buffed, 0.30)
        self.assertGreater(buffed, plain + 0.02)

    def test_a_crowd_of_buffs_lifts_her_off_the_impossible_chart(self) -> None:
        # Unbuffed: rank 0 against rank 20 is chart -8, which has no Success (1).
        alone = perform_check_with_modifiers(
            self.ysmay, self.climbing, target_difficulty=RANK_TWENTY
        )
        self.assertEqual(alone.rank_difference, -8)
        self.assertEqual(alone.standing.slid.at_least(1), 0)
        for index in range(10):
            self.buff(12, f"Admirer {index + 1}")
        self.buff(30, "A sworn blessing")
        # +150 points: 155 is rank 18 (starts at 154) against rank 20: -1.875, chart -2, winnable.
        result = perform_check_with_modifiers(
            self.ysmay, self.climbing, target_difficulty=RANK_TWENTY
        )
        self.assertEqual(result.total_points, 155)
        self.assertEqual(result.rank_difference, -2)
        self.assertEqual(result.standing.chart.rank_difference, -2)
        self.assertGreater(result.standing.slid.at_least(1), 0)
        # The same odds as a character whose own total is 155 with no buffs at all.
        self.assertEqual(
            result.standing.slid.at_least(1), resolve_standing(155, RANK_TWENTY).slid.at_least(1)
        )

    def test_too_few_buffs_leave_her_on_the_impossible_chart(self) -> None:
        # +3 points: 8 of rank 0's 18 points against rank 8, -7.56. Short of the next rank, so
        # the roll stays on chart -8 and slides toward -7 over chart -8's own outcomes only.
        self.buff(3, "A word of encouragement")
        result = perform_check_with_modifiers(
            self.ysmay, self.climbing, target_difficulty=RANK_EIGHT
        )
        self.assertEqual(result.total_points, 8)
        self.assertEqual(result.rank_difference, -8)
        self.assertEqual(result.standing.chart.rank_difference, -8)
        self.assertFalse(
            [band for band in result.standing.slid.bands if band.outcome.success_level >= 1]
        )
        self.assertEqual(result.standing.slid.at_least(1), 0)

    def test_at_a_three_rank_gap_the_buffs_count_in_full(self) -> None:
        # Own standing against Competent (rank 3): -2.72, chart -3 (12% Success or better)
        # slid 5/18 toward chart -2 (15%): 12% + 5/18 x 3% = 12.83%.
        alone = self.success_odds(COMPETENT)
        self.buff(24, "A rousing speech")
        buffed = self.success_odds(COMPETENT)
        # 29 points: rank 2 (starts at 26), 3/8 through; -0.625, chart -1 (22%) slid 3/8
        # toward chart 0 (40%): 22% + 3/8 x 18% = 28.75%.
        self.assertAlmostEqual(alone, 0.12 + 5 / 18 * 0.03)
        self.assertAlmostEqual(buffed, 0.2875)

    def test_the_preview_grades_on_her_full_total(self) -> None:
        """The grade the action lists and standoff cards show: Impossible at her total,
        and no longer Impossible once enough buffs lift her onto a winnable chart."""
        for modifiers, impossible in ((0, True), (3, True), (150, False)):
            difference = preview_check_difficulty(
                self.ysmay, self.climbing, RANK_TWENTY, extra_modifiers=modifiers
            )
            with self.subTest(modifiers=modifiers):
                self.assertEqual(
                    difficulty_indicator_for_rank_difference(difference)
                    == DifficultyIndicator.IMPOSSIBLE,
                    impossible,
                )

    def test_a_tapered_pile_is_what_counts(self) -> None:
        """With #4594's light taper on condition buffs, the tapered pile is the modifier
        total the slide reads."""
        ModifierTaper.objects.create(
            lane=ModifierLane.CHECK,
            source_kind=ModifierSourceKind.CONDITION,
            ratio=Decimal("0.8750"),
            floor=Decimal("0.6667"),
        )
        for index in range(10):
            self.buff(12, f"Admirer {index + 1}")
        result = perform_check_with_modifiers(
            self.ysmay, self.climbing, target_difficulty=RANK_THIRTEEN
        )
        # 12 x (1 + 7/8 + (7/8)^2 + (7/8)^3 + 6 x 2/3) = 87.7 -> 88, not the plain 120.
        self.assertEqual(result.total_points, 5 + 88)
        # 93 points: Master (rank 10, starts at 90), 3/8 through, against rank 13: chart -3.
        self.assertEqual(
            result.standing.roller.text, "Master (rank 10), 38% toward Rank 11 (rank 11)"
        )
        self.assertEqual(result.rank_difference, -3)
        self.assertGreater(result.standing.slid.at_least(1), 0)

"""Journeys for the slide and the hopeless rule (#4601, slice b of #4551).

Ysmay, a level-1 character, rolls the same check again and again through the real check
pipeline (``perform_check_with_modifiers``, which gathers her conditions), with the
seeded rank ladder and result charts. Her own total is 5 points: Incompetent (rank 0),
50% toward Novice (rank 1). Buffs are real conditions on her with check modifiers. The
dice are seeded so each run is the same, and each rate is far from what whole-rank
charts would give.
"""

from __future__ import annotations

import random

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.services import perform_check_with_modifiers, preview_check_difficulty
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.services import difficulty_indicator_for_rank_difference
from world.seeds.checks import seed_check_resolution_tables
from world.traits.models import ResultChart

ROLLS = 800
NOVICE = 10  # Novice (rank 1), 0% through its band
EXPERT = 50  # Expert (rank 3)
LEGENDARY = 200  # Legendary (rank 7)


class EveryPointCounts(JourneyCase):
    """A check's odds slide with every point, and a hopeless check stays hopeless."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        ResultChart.clear_cache()
        self.climbing = CheckTypeFactory(name="Climbing", description="Scale a wall or a cliff.")
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        random.seed(4601)

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

    def roll(self, difficulty: int) -> dict[int, float]:
        """Roll ``ROLLS`` times; the share of each success level."""
        counts: dict[int, int] = {}
        for _ in range(ROLLS):
            level = perform_check_with_modifiers(
                self.ysmay, self.climbing, target_difficulty=difficulty
            ).success_level
            counts[level] = counts.get(level, 0) + 1
        return {level: count / ROLLS for level, count in counts.items()}

    @staticmethod
    def at_least(shares: dict[int, float], level: int) -> float:
        return sum(share for lv, share in shares.items() if lv >= level)

    def test_her_result_says_where_she_stood(self) -> None:
        result = perform_check_with_modifiers(self.ysmay, self.climbing, target_difficulty=NOVICE)
        self.assertEqual(result.total_points, 5)
        self.assertEqual(
            result.standing_text,
            "Incompetent (rank 0), 50% toward Novice (rank 1) against Novice (rank 1)",
        )
        self.assertEqual(result.rank_difference, -1)

        # Rolled at the table, her own message carries it; the room's narration does not.
        self.telnet(self.ysmay, "scene start")
        told = self.telnet(self.ysmay, "check Climbing at trivial")
        self.assertIn(
            "Your standing: Incompetent (rank 0), 50% toward Novice (rank 1) against "
            "Novice (rank 1), 33% toward Competent (rank 2).",
            told,
        )

    def test_halfway_through_a_band_she_gets_the_halfway_odds(self) -> None:
        # Chart -1 (22% Success or better) slid 50% toward chart 0 (40% once its
        # Critical Success counts as Success): 31%. Whole ranks would give 22%.
        shares = self.roll(NOVICE)
        self.assertAlmostEqual(self.at_least(shares, 1), 0.31, delta=0.045)
        self.assertEqual(shares.get(2, 0), 0)

    def test_one_small_buff_moves_the_odds(self) -> None:
        plain = self.at_least(self.roll(NOVICE), 1)
        # +3 keeps her in Incompetent (rank 0); whole ranks would ignore it.
        self.buff(3, "A word of encouragement")
        buffed = self.at_least(self.roll(NOVICE), 1)
        # 80% through the band: 22% + 0.8 x 18% = 36.4%.
        self.assertAlmostEqual(buffed, 0.364, delta=0.045)
        self.assertGreater(buffed, plain + 0.02)

    def test_a_crowd_of_buffs_never_wins_a_hopeless_check(self) -> None:
        # Own standing: Incompetent (rank 0), 50% through, against Legendary (rank 7):
        # chart -7, which has no Success (1).
        alone = self.roll(LEGENDARY)
        for index in range(10):
            self.buff(12, f"Admirer {index + 1}")
        self.buff(30, "A sworn blessing")
        # +150 points: Peerless (rank 6). Without the hopeless rule that is chart -1,
        # 22% Success or better.
        result = perform_check_with_modifiers(
            self.ysmay, self.climbing, target_difficulty=LEGENDARY
        )
        self.assertEqual(result.total_points, 155)
        self.assertTrue(result.standing.hopeless)
        self.assertTrue(result.standing.pinned)
        self.assertEqual(result.rank_difference, -7)

        adored = self.roll(LEGENDARY)
        self.assertEqual(self.at_least(adored, 1), 0)
        # The buffs still soften the loss: less Botch (-2), more Partial Success (0).
        self.assertLess(adored.get(-2, 0), alone.get(-2, 0))
        self.assertGreater(adored.get(0, 0), alone.get(0, 0))

    def test_at_a_three_rank_gap_the_buffs_count_in_full(self) -> None:
        # Own standing against Expert (rank 3): chart -3 at 50%, 13.5% Success or better.
        alone = self.at_least(self.roll(EXPERT), 1)
        self.buff(40, "A rousing speech")
        buffed = self.at_least(self.roll(EXPERT), 1)
        # 45 points: Competent (rank 2), 80% toward Expert; chart -1 at 80%: 36.4%.
        self.assertAlmostEqual(alone, 0.135, delta=0.04)
        self.assertAlmostEqual(buffed, 0.364, delta=0.045)

    def test_the_preview_grades_impossible_on_her_own_standing(self) -> None:
        """The grade the action lists and standoff cards show: a buff never lifts it."""
        for modifiers in (0, 150):
            difference = preview_check_difficulty(
                self.ysmay, self.climbing, LEGENDARY, extra_modifiers=modifiers
            )
            with self.subTest(modifiers=modifiers):
                self.assertEqual(
                    difficulty_indicator_for_rank_difference(difference),
                    DifficultyIndicator.IMPOSSIBLE,
                )
        difference = preview_check_difficulty(self.ysmay, self.climbing, EXPERT)
        self.assertNotEqual(
            difficulty_indicator_for_rank_difference(difference), DifficultyIndicator.IMPOSSIBLE
        )

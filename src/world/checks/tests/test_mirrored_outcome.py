"""mirrored_outcome: a resisting PC's outcome read from the acting NPC's side (#4418)."""

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.checks.services import mirrored_outcome
from world.checks.types import CheckResult
from world.traits.factories import CheckOutcomeFactory


class MirroredOutcomeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcomes = {
            level: CheckOutcomeFactory(name=f"Mirror {level}", success_level=level)
            for level in (-2, -1, 1, 2)
        }

    def test_mirrored_result_preserves_roll_and_original(self) -> None:
        result = CheckResult(
            check_type=CheckTypeFactory(),
            outcome=self.outcomes[2],
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=3,
            trait_points=21,
            aspect_bonus=4,
            total_points=25,
            effective_roll=73,
        )
        mirrored = result.with_outcome(mirrored_outcome(result.outcome))
        self.assertIsNot(mirrored, result)
        self.assertEqual(mirrored.outcome, self.outcomes[-2])
        self.assertEqual(result.outcome, self.outcomes[2])
        self.assertEqual(
            (mirrored.rank_difference, mirrored.total_points, mirrored.effective_roll), (3, 25, 73)
        )
        self.assertIs(mirrored.check_type, result.check_type)

    def test_success_mirrors_to_failure(self) -> None:
        self.assertEqual(mirrored_outcome(self.outcomes[2]).success_level, -2)
        self.assertEqual(mirrored_outcome(self.outcomes[-1]).success_level, 1)

    def test_no_exact_row_takes_the_nearest_on_the_same_side(self) -> None:
        triumph = CheckOutcomeFactory(name="Mirror 3", success_level=3)
        self.assertEqual(mirrored_outcome(triumph).success_level, -2)

    def test_zero_mirrors_to_itself(self) -> None:
        middling = CheckOutcomeFactory(name="Mirror 0", success_level=0)
        self.assertEqual(mirrored_outcome(middling), middling)

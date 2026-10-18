"""mirrored_outcome: a resisting PC's outcome read from the acting NPC's side (#4418)."""

from django.test import TestCase

from world.checks.services import mirrored_outcome
from world.traits.factories import CheckOutcomeFactory


class MirroredOutcomeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcomes = {
            level: CheckOutcomeFactory(name=f"Mirror {level}", success_level=level)
            for level in (-2, -1, 1, 2)
        }

    def test_success_mirrors_to_failure(self) -> None:
        self.assertEqual(mirrored_outcome(self.outcomes[2]).success_level, -2)
        self.assertEqual(mirrored_outcome(self.outcomes[-1]).success_level, 1)

    def test_no_exact_row_takes_the_nearest_on_the_same_side(self) -> None:
        triumph = CheckOutcomeFactory(name="Mirror 3", success_level=3)
        self.assertEqual(mirrored_outcome(triumph).success_level, -2)

    def test_zero_with_no_zero_row_mirrors_to_nothing(self) -> None:
        self.assertIsNone(mirrored_outcome(CheckOutcomeFactory.build(success_level=0)))

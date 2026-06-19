"""RenownAwardConfig abstract base — verified through DramaticMomentType (#953)."""

from django.test import TestCase

from world.magic.factories import DramaticMomentTypeFactory
from world.societies.constants import RenownMagnitude, RenownReach, RenownRisk


class RenownAwardConfigTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.moment_type = DramaticMomentTypeFactory(
            magnitude=RenownMagnitude.HIGH,
            risk=RenownRisk.MODERATE,
            reach=RenownReach.REGIONAL,
        )

    def test_as_renown_award_kwargs_returns_award_inputs(self):
        kwargs = self.moment_type.as_renown_award_kwargs()
        self.assertEqual(kwargs["magnitude"], RenownMagnitude.HIGH)
        self.assertEqual(kwargs["risk"], RenownRisk.MODERATE)
        self.assertEqual(kwargs["reach"], RenownReach.REGIONAL)
        self.assertEqual(list(kwargs["archetypes"]), [])

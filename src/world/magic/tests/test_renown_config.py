"""RenownAwardConfig abstract base — verified through DramaticMomentType (#953)."""

from django.test import TestCase

from world.magic.factories import DramaticMomentTypeFactory, ensure_audere_majora_threshold
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


class AudereMajoraRenownConfigTests(TestCase):
    def test_threshold_mints_a_deed_by_default(self):
        """Helper threshold must carry risk != NONE so a crossing yields legend."""
        threshold = ensure_audere_majora_threshold()
        self.assertNotEqual(threshold.risk, RenownRisk.NONE)
        kwargs = threshold.as_renown_award_kwargs()
        self.assertIn("magnitude", kwargs)

    def test_deed_title_blank_by_default(self):
        threshold = ensure_audere_majora_threshold()
        self.assertEqual(threshold.deed_title, "")

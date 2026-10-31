from django.core.exceptions import ValidationError
from django.test import TestCase

from world.magic.factories import FuryConfigFactory, FuryDegreeShareFactory, FuryTierFactory
from world.magic.models import FuryConfig, FuryTier
from world.traits.factories import CheckOutcomeFactory


class FuryModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.smouldering = FuryTierFactory(name="Smouldering", depth=1, control_surrendered=2)
        cls.berserk = FuryTierFactory(
            name="Berserk", depth=3, control_surrendered=8, berserk_severity=5
        )

    def test_tiers_order_by_depth(self):
        names = list(FuryTier.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Smouldering", "Berserk"])

    def test_natural_key_roundtrip(self):
        self.assertEqual(FuryTier.objects.get_by_natural_key("Berserk"), self.berserk)

    def test_config_is_singleton(self):
        c1 = FuryConfigFactory()
        c2 = FuryConfigFactory()
        self.assertEqual(c1.pk, 1)
        self.assertEqual(c2.pk, 1)
        self.assertEqual(FuryConfig.objects.count(), 1)


class FuryDegreeShareCleanTests(TestCase):
    """A better outcome never buys a smaller percent than a worse one (#4738)."""

    @classmethod
    def setUpTestData(cls):
        cls.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.partial = CheckOutcomeFactory(name="Partial", success_level=0)
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        FuryDegreeShareFactory(outcome_tier=cls.partial, intensity_percent=50)

    def test_a_better_outcome_buying_less_is_refused(self):
        share = FuryDegreeShareFactory.build(outcome_tier=self.success, intensity_percent=25)
        with self.assertRaises(ValidationError):
            share.full_clean()

    def test_a_worse_outcome_buying_more_is_refused(self):
        share = FuryDegreeShareFactory.build(outcome_tier=self.failure, intensity_percent=75)
        with self.assertRaises(ValidationError):
            share.full_clean()

    def test_a_monotonic_row_is_accepted(self):
        share = FuryDegreeShareFactory.build(outcome_tier=self.success, intensity_percent=100)
        share.full_clean()

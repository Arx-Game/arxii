from django.test import TestCase

from world.magic.factories import FuryConfigFactory, FuryTierFactory
from world.magic.models import FuryConfig, FuryTier


class FuryModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.smouldering = FuryTierFactory(
            name="Smouldering",
            depth=1,
            control_penalty=2,
            intensity_bonus=2,
            lucid_grade_floor=1,
            berserk_severity=0,
        )
        cls.berserk = FuryTierFactory(
            name="Berserk",
            depth=3,
            control_penalty=8,
            intensity_bonus=10,
            lucid_grade_floor=3,
            berserk_severity=5,
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

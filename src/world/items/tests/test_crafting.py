from django.test import TestCase

from world.items.factories import QualityTierFactory


class QualityTierForScoreTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.common = QualityTierFactory(name="Common", numeric_min=0, numeric_max=29, sort_order=0)
        cls.fine = QualityTierFactory(name="Fine", numeric_min=30, numeric_max=69, sort_order=1)
        cls.master = QualityTierFactory(
            name="Masterwork", numeric_min=70, numeric_max=200, sort_order=2
        )

    def test_score_resolves_to_containing_tier(self) -> None:
        from world.items.models import QualityTier

        self.assertEqual(QualityTier.for_score(10), self.common)
        self.assertEqual(QualityTier.for_score(30), self.fine)
        self.assertEqual(QualityTier.for_score(69), self.fine)
        self.assertEqual(QualityTier.for_score(150), self.master)

    def test_below_all_ranges_clamps_to_lowest(self) -> None:
        from world.items.models import QualityTier

        self.assertEqual(QualityTier.for_score(-5), self.common)

    def test_above_all_ranges_clamps_to_highest(self) -> None:
        from world.items.models import QualityTier

        self.assertEqual(QualityTier.for_score(9999), self.master)


class FacetCraftingConfigTests(TestCase):
    def test_get_is_lazy_singleton(self) -> None:
        from world.items.services.crafting import get_facet_crafting_config

        cfg1 = get_facet_crafting_config()
        cfg2 = get_facet_crafting_config()
        self.assertEqual(cfg1.pk, 1)
        self.assertEqual(cfg1.pk, cfg2.pk)
        self.assertIsNone(cfg1.check_type)
        self.assertGreaterEqual(cfg1.min_success_level, 1)

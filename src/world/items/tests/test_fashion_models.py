from django.test import TestCase

from world.items.factories import FashionStyleBonusFactory, FashionStyleFactory
from world.magic.factories import FacetFactory


class FashionStyleModelTests(TestCase):
    def test_style_carries_in_vogue_facets(self):
        style = FashionStyleFactory()
        facet = FacetFactory()
        style.in_vogue_facets.add(facet)
        self.assertIn(facet, style.in_vogue_facets.all())

    def test_bonus_unique_per_style_target(self):
        bonus = FashionStyleBonusFactory(weight=2)
        self.assertEqual(bonus.fashion_style.bonuses.get(target=bonus.target).weight, 2)

    def test_natural_key_is_name(self):
        style = FashionStyleFactory(name="Predatory Elegance")
        self.assertEqual(str(style), "Predatory Elegance")

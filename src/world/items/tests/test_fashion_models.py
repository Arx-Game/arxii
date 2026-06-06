from django.db import IntegrityError, transaction
from django.test import TestCase

from world.items.factories import FashionStyleBonusFactory, FashionStyleFactory
from world.items.models import FashionStyle, FashionStyleBonus
from world.magic.factories import FacetFactory


class FashionStyleModelTests(TestCase):
    def test_style_carries_in_vogue_facets(self):
        style = FashionStyleFactory()
        facet = FacetFactory()
        style.in_vogue_facets.add(facet)
        self.assertIn(facet, style.in_vogue_facets.all())

    def test_bonus_unique_per_style_target(self):
        bonus = FashionStyleBonusFactory()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FashionStyleBonus.objects.create(
                    fashion_style=bonus.fashion_style,
                    target=bonus.target,
                    weight=99,
                )

    def test_str_returns_name(self):
        style = FashionStyleFactory(name="Predatory Elegance")
        self.assertEqual(str(style), "Predatory Elegance")

    def test_get_by_natural_key(self):
        style = FashionStyleFactory(name="Predatory Elegance")
        found = FashionStyle.objects.get_by_natural_key("Predatory Elegance")
        self.assertEqual(found.pk, style.pk)

    def test_bonus_weight_survives_round_trip(self):
        bonus = FashionStyleBonusFactory(weight=7)
        bonus.refresh_from_db()
        self.assertEqual(bonus.weight, 7)

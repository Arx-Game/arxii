from django.test import TestCase

from world.items.factories import FashionStyleFactory
from world.societies.factories import SocietyFactory


class SocietyFashionRotationTests(TestCase):
    def test_society_points_at_current_style(self):
        style = FashionStyleFactory()
        society = SocietyFactory(current_fashion_style=style)
        self.assertEqual(society.current_fashion_style, style)

    def test_current_style_nullable(self):
        self.assertIsNone(SocietyFactory().current_fashion_style)

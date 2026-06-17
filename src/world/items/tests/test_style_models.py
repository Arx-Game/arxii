"""Tests for the Style vocabulary model."""

from django.test import TestCase

from world.items.factories import StyleFactory
from world.items.models import Style


class StyleModelTests(TestCase):
    def test_style_natural_key_roundtrip(self) -> None:
        style = StyleFactory(name="Seductive", description="Alluring presentation.")
        self.assertEqual(Style.objects.get_by_natural_key("Seductive"), style)
        self.assertEqual(str(style), "Seductive")

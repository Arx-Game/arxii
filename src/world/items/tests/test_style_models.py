"""Tests for the Style vocabulary model and ItemStyle tag."""

from django.db import IntegrityError
from django.test import TestCase

from world.items.factories import (
    ItemInstanceFactory,
    ItemStyleFactory,
    QualityTierFactory,
    StyleFactory,
)
from world.items.models import ItemStyle, Style


class StyleModelTests(TestCase):
    def test_style_natural_key_roundtrip(self) -> None:
        style = StyleFactory(name="Seductive", description="Alluring presentation.")
        self.assertEqual(Style.objects.get_by_natural_key("Seductive"), style)
        self.assertEqual(str(style), "Seductive")


class ItemStyleTests(TestCase):
    def test_item_carries_styles(self) -> None:
        inst = ItemInstanceFactory(template__style_capacity=2)
        ItemStyleFactory(item_instance=inst, style__name="Seductive")
        ItemStyleFactory(item_instance=inst, style__name="Sinister")
        self.assertEqual(len(inst.cached_item_styles), 2)

    def test_duplicate_style_on_instance_raises(self) -> None:
        inst = ItemInstanceFactory(template__style_capacity=1)
        style = StyleFactory(name="Regal")
        tier = QualityTierFactory()
        ItemStyle.objects.create(item_instance=inst, style=style, attachment_quality_tier=tier)
        with self.assertRaises(IntegrityError):
            ItemStyle.objects.create(item_instance=inst, style=style, attachment_quality_tier=tier)

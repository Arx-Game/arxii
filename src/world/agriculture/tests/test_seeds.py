"""Tests for agriculture seed functions."""

from django.test import TestCase

from world.agriculture.seeds import (
    ensure_field_granary_kinds,
    ensure_starter_crop_types,
)


class SeedTests(TestCase):
    def test_ensure_field_granary_kinds_idempotent(self):
        kind1 = ensure_field_granary_kinds()
        kind2 = ensure_field_granary_kinds()
        self.assertEqual(kind1.pk, kind2.pk)

    def test_ensure_starter_crop_types_idempotent(self):
        ensure_starter_crop_types()
        ensure_starter_crop_types()
        from world.agriculture.models import CropType

        self.assertGreaterEqual(CropType.objects.count(), 3)

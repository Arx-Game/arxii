"""Tests for ClashConfig.clash_min_intensity field."""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import ClashConfigFactory
from world.combat.models import ClashConfig


class ClashConfigMinIntensityTests(TestCase):
    """Verify the field, default, and tunability."""

    def test_default_is_four(self) -> None:
        config = ClashConfigFactory()
        self.assertEqual(config.clash_min_intensity, 0)

    def test_tunable(self) -> None:
        config = ClashConfigFactory()
        config.clash_min_intensity = 7
        config.save(update_fields=["clash_min_intensity"])

        config.refresh_from_db()
        self.assertEqual(config.clash_min_intensity, 7)

    def test_field_definition(self) -> None:
        field = ClashConfig._meta.get_field("clash_min_intensity")
        self.assertEqual(field.default, 0)
        self.assertFalse(field.null)
        # PositiveIntegerField → internal type
        self.assertEqual(field.get_internal_type(), "PositiveIntegerField")

"""Tests for GiftAcquisitionConfig technique-progress fields (#2711)."""

from decimal import Decimal

from django.test import TestCase

from world.magic.models import GiftAcquisitionConfig
from world.magic.services.gift_acquisition import get_gift_acquisition_config


class GiftAcquisitionConfigProgressFieldsTest(TestCase):
    def test_defaults(self):
        """New config fields have correct defaults."""
        GiftAcquisitionConfig.objects.all().delete()
        config = get_gift_acquisition_config()
        self.assertEqual(config.cross_path_cost_multiplier, Decimal("2.00"))
        self.assertEqual(config.weekly_training_cap, 50)
        self.assertEqual(config.cross_path_cap_divisor, 1)

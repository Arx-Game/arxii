"""Model tests for the agriculture app."""

from django.db import IntegrityError
from django.test import TestCase

from world.agriculture.models import (
    CropType,
    FoodStockpile,
)


class CropTypeTests(TestCase):
    def test_create_crop_type(self):
        crop = CropType.objects.create(
            name="Wheat",
            base_production=10,
            description="A staple grain.",
        )
        self.assertEqual(crop.name, "Wheat")
        self.assertEqual(crop.base_production, 10)
        self.assertEqual(str(crop), "Wheat")

    def test_name_unique(self):
        CropType.objects.create(name="Barley", base_production=8)
        with self.assertRaises(IntegrityError):
            CropType.objects.create(name="Barley", base_production=12)


class FoodConfigTests(TestCase):
    def test_singleton_lazy_create(self):
        from world.agriculture.services import get_food_config

        config = get_food_config()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.production_rate_multiplier, 1)
        self.assertEqual(config.consumption_per_capita, 1)
        self.assertEqual(config.granary_capacity_per_level, 100)
        # Calling again returns the same row
        config2 = get_food_config()
        self.assertEqual(config2.pk, config.pk)


class FoodStockpileTests(TestCase):
    def test_defaults(self):
        from world.areas.factories import AreaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        domain = Domain.objects.create(
            area=AreaFactory(),
            name="Test Domain",
            owner_org=org,
        )
        stockpile = FoodStockpile.objects.create(domain=domain)
        self.assertEqual(stockpile.stored, 0)
        self.assertIsNone(stockpile.last_collected_at)

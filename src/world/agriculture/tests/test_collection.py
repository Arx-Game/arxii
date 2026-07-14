"""Tests for the food collection dispatch."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.agriculture.types import FoodCollectionResult


def _make_field(pool=100):
    """Helper: create a Field instance with a crop and uncollected pool."""
    from world.agriculture.models import CropType, FieldDetails
    from world.room_features.constants import (
        RoomFeatureInstallMechanism,
        RoomFeatureServiceStrategy,
    )
    from world.room_features.factories import RoomFeatureInstanceFactory
    from world.room_features.models import RoomFeatureKind

    kind = RoomFeatureKind.objects.create(
        name="Field",
        max_level=5,
        service_strategy=RoomFeatureServiceStrategy.FIELD,
        install_mechanism=RoomFeatureInstallMechanism.PROJECT,
    )
    crop = CropType.objects.create(name="Wheat", base_production=10)
    instance = RoomFeatureInstanceFactory(feature_kind=kind)
    FieldDetails.objects.create(feature_instance=instance, crop_type=crop, uncollected_pool=pool)
    return instance


class CollectFieldFoodTests(TestCase):
    def test_no_pool_raises(self):
        from world.agriculture.services import collect_field_food

        instance = _make_field(pool=0)
        with self.assertRaises(ValueError):
            collect_field_food(MagicMock(), instance)

    def test_collection_zeroes_pool(self):
        from world.agriculture.models import FieldDetails
        from world.agriculture.services import collect_field_food

        instance = _make_field(pool=100)

        # No check type seeded → success_level defaults to 0 → 85% band
        # No domain → all overflow.  location=None so no emit_event dispatch.
        result = collect_field_food(MagicMock(location=None), instance)
        self.assertIsInstance(result, FoodCollectionResult)
        self.assertEqual(result.gathered, 100)
        self.assertFalse(result.catastrophe)
        self.assertEqual(result.landed, 0)
        self.assertEqual(result.overflow, 85)

        details = FieldDetails.objects.get(feature_instance=instance)
        self.assertEqual(details.uncollected_pool, 0)

    def test_no_field_details_raises(self):
        from world.agriculture.services import collect_field_food
        from world.room_features.constants import (
            RoomFeatureInstallMechanism,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.factories import RoomFeatureInstanceFactory
        from world.room_features.models import RoomFeatureKind

        kind = RoomFeatureKind.objects.create(
            name="Field2",
            max_level=5,
            service_strategy=RoomFeatureServiceStrategy.FIELD,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        with self.assertRaises(ValueError):
            collect_field_food(MagicMock(), instance)


class UnrestSkimTests(TestCase):
    """#2238 — unrest skims the food haul on the way into the stockpile."""

    def test_no_unrest_no_skim(self):
        from world.agriculture.services.collection import _apply_unrest_skim

        self.assertEqual(_apply_unrest_skim(100, 0), 100)

    def test_unrest_skims_proportionally(self):
        from world.agriculture.services.collection import _apply_unrest_skim

        self.assertEqual(_apply_unrest_skim(100, 40), 60)  # 40% skimmed

    def test_skim_is_capped(self):
        from world.agriculture.services.collection import _apply_unrest_skim

        # unrest 100 caps at UNREST_COLLECTION_SKIM_MAX_PCT (60) → only 40% lands.
        self.assertEqual(_apply_unrest_skim(100, 100), 40)

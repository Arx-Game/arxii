"""Tests for the CollectFoodAction."""

from unittest.mock import MagicMock

from django.test import TestCase


class CollectFoodActionTests(TestCase):
    def test_no_field_instance_returns_failure(self):
        from actions.definitions.collect_food import CollectFoodAction

        action = CollectFoodAction()
        result = action.execute(MagicMock(), field_instance=None)
        self.assertFalse(result.success)

    def test_successful_collection(self):
        from actions.definitions.collect_food import CollectFoodAction
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
        FieldDetails.objects.create(feature_instance=instance, crop_type=crop, uncollected_pool=50)

        action = CollectFoodAction()
        result = action.execute(MagicMock(), field_instance=instance)

        self.assertTrue(result.success)
        self.assertIn("landed", result.data)

    def test_empty_pool_returns_failure(self):
        from actions.definitions.collect_food import CollectFoodAction
        from world.agriculture.models import CropType, FieldDetails
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
        crop = CropType.objects.create(name="Oats", base_production=5)
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        FieldDetails.objects.create(feature_instance=instance, crop_type=crop, uncollected_pool=0)

        action = CollectFoodAction()
        result = action.execute(MagicMock(), field_instance=instance)

        self.assertFalse(result.success)

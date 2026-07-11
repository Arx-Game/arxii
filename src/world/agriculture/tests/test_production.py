"""Tests for agriculture production and domain resolution services."""

from django.test import TestCase

from world.agriculture.services import (
    field_production_tick,
    max_food_capacity,
    resolve_domain_for_feature,
)


class FieldProductionTickTests(TestCase):
    def test_no_fields_no_op(self):
        result = field_production_tick()
        self.assertEqual(result["fields_processed"], 0)
        self.assertEqual(result["food_accrued"], 0)

    def test_accrues_food_into_pool(self):
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
        instance = RoomFeatureInstanceFactory(feature_kind=kind, level=2)
        FieldDetails.objects.create(feature_instance=instance, crop_type=crop)

        result = field_production_tick()
        self.assertEqual(result["fields_processed"], 1)

        details = FieldDetails.objects.get(feature_instance=instance)
        # base_production(10) × level(2) × multiplier(1) = 20
        self.assertEqual(details.uncollected_pool, 20)


class MaxFoodCapacityTests(TestCase):
    def test_no_granaries_returns_zero(self):
        from world.areas.factories import AreaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        domain = Domain.objects.create(area=AreaFactory(), name="Test", owner_org=org)
        self.assertEqual(max_food_capacity(domain), 0)


class ResolveDomainTests(TestCase):
    def test_returns_none_for_no_domain(self):
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
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        self.assertIsNone(resolve_domain_for_feature(instance))

"""Tests for the CollectFoodAction."""

from unittest.mock import MagicMock

from django.test import TestCase


class CollectFoodActionTests(TestCase):
    def test_no_field_instance_returns_failure(self):
        from actions.definitions.collect_food import CollectFoodAction

        # No explicit field and no field resolvable from the (locationless) actor → failure.
        action = CollectFoodAction()
        result = action.execute(MagicMock(location=None), field_instance=None)
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
        result = action.execute(MagicMock(location=None), field_instance=instance)

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
        result = action.execute(MagicMock(location=None), field_instance=instance)

        self.assertFalse(result.success)


def _make_field(*, pool: int, name: str = "Field"):
    """A Field RoomFeatureInstance with a crop and an uncollected pool."""
    from world.agriculture.models import CropType, FieldDetails
    from world.room_features.constants import (
        RoomFeatureInstallMechanism,
        RoomFeatureServiceStrategy,
    )
    from world.room_features.factories import RoomFeatureInstanceFactory
    from world.room_features.models import RoomFeatureKind

    kind = RoomFeatureKind.objects.create(
        name=name,
        max_level=5,
        service_strategy=RoomFeatureServiceStrategy.FIELD,
        install_mechanism=RoomFeatureInstallMechanism.PROJECT,
    )
    crop = CropType.objects.create(name=f"{name}Crop", base_production=10)
    instance = RoomFeatureInstanceFactory(feature_kind=kind)
    FieldDetails.objects.create(feature_instance=instance, crop_type=crop, uncollected_pool=pool)
    return instance


class CollectFoodResolutionTests(TestCase):
    """#2237 — the action resolves its Field from a raw id (REST) or the actor's room (telnet)."""

    def test_resolves_field_by_id_the_rest_dispatch_shape(self):
        # The REST path passes a raw int field_instance_id with no upstream ObjectDB resolution.
        from actions.definitions.collect_food import CollectFoodAction

        instance = _make_field(pool=50, name="RestField")
        result = CollectFoodAction().execute(
            MagicMock(location=None), field_instance_id=instance.pk
        )
        self.assertTrue(result.success)
        self.assertIn("landed", result.data)

    def test_resolves_field_in_the_actors_room_the_telnet_shape(self):
        from actions.definitions.collect_food import CollectFoodAction

        instance = _make_field(pool=50, name="RoomField")
        actor = MagicMock()
        actor.location = instance.room_profile.objectdb
        result = CollectFoodAction().execute(actor)  # no field kwargs — resolve from the room
        self.assertTrue(result.success)

    def test_unknown_field_id_returns_failure(self):
        from actions.definitions.collect_food import CollectFoodAction

        result = CollectFoodAction().execute(MagicMock(location=None), field_instance_id=999999)
        self.assertFalse(result.success)
        self.assertIn("field", result.message.lower())

    def test_no_room_and_no_field_returns_failure(self):
        from actions.definitions.collect_food import CollectFoodAction

        actor = MagicMock()
        actor.location = None
        result = CollectFoodAction().execute(actor)
        self.assertFalse(result.success)

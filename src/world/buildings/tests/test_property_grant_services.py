"""Tests for the PropertyGrantProfile model and world.buildings.property_grant_services."""

from django.test import TestCase

from world.buildings.constants import ConditionTier
from world.buildings.factories import BuildingKindFactory, PropertyGrantProfileFactory
from world.buildings.models import PropertyGrantProfile


class PropertyGrantProfileModelTests(TestCase):
    def test_profile_defaults(self):
        profile = PropertyGrantProfileFactory()
        assert profile.initial_condition_tier == ConditionTier.DECAYED
        assert profile.activation_target_tier is None
        assert profile.activation_cost_floor_coppers == 0

    def test_profile_str_is_name(self):
        profile = PropertyGrantProfileFactory(name="Test Grant Profile")
        assert str(profile) == "Test Grant Profile"

    def test_profile_name_unique(self):
        PropertyGrantProfileFactory(name="Dup")
        with self.assertRaises(Exception):  # noqa: B017 — IntegrityError vs ValidationError varies
            PropertyGrantProfile.objects.create(name="Dup", building_kind=BuildingKindFactory())

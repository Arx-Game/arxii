"""Tests for obstacle system models."""

from django.db import IntegrityError
from django.test import TestCase

from world.obstacles.constants import DiscoveryType, ResolutionType
from world.obstacles.factories import BypassOptionFactory, ObstaclePropertyFactory
from world.obstacles.models import ObstacleProperty


class ObstaclePropertyModelTest(TestCase):
    """Tests for ObstacleProperty model."""

    def test_create_property(self) -> None:
        prop = ObstaclePropertyFactory(name="solid")
        assert prop.name == "solid"
        assert str(prop) == "solid"

    def test_name_unique(self) -> None:
        ObstaclePropertyFactory(name="solid")
        with self.assertRaises(IntegrityError):
            ObstacleProperty.objects.create(name="solid")


class BypassOptionModelTest(TestCase):
    """Tests for BypassOption model."""

    def test_create_bypass_option(self) -> None:
        prop = ObstaclePropertyFactory(name="tall")
        bypass = BypassOptionFactory(
            obstacle_property=prop,
            name="Fly Over",
            discovery_type=DiscoveryType.OBVIOUS,
            resolution_type=ResolutionType.PERSONAL,
        )
        assert bypass.name == "Fly Over"
        assert bypass.obstacle_property == prop
        assert bypass.discovery_type == DiscoveryType.OBVIOUS
        assert bypass.resolution_type == ResolutionType.PERSONAL
        assert str(bypass) == "Fly Over (tall)"

    def test_bypass_option_unique_per_property(self) -> None:
        prop = ObstaclePropertyFactory(name="tall")
        BypassOptionFactory(obstacle_property=prop, name="Fly Over")
        with self.assertRaises(IntegrityError):
            BypassOptionFactory(obstacle_property=prop, name="Fly Over")

    def test_different_properties_same_bypass_name(self) -> None:
        prop1 = ObstaclePropertyFactory(name="tall")
        prop2 = ObstaclePropertyFactory(name="wide")
        BypassOptionFactory(obstacle_property=prop1, name="Fly Over")
        bypass2 = BypassOptionFactory(obstacle_property=prop2, name="Fly Over")
        assert bypass2.name == "Fly Over"

    def test_temporary_resolution_with_duration(self) -> None:
        bypass = BypassOptionFactory(
            resolution_type=ResolutionType.TEMPORARY,
            resolution_duration_rounds=5,
        )
        assert bypass.resolution_duration_rounds == 5

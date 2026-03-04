"""Tests for obstacle system models."""

from django.db import IntegrityError
from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.conditions.factories import CapabilityTypeFactory
from world.obstacles.constants import DiscoveryType, ResolutionType
from world.obstacles.factories import (
    BypassCapabilityRequirementFactory,
    BypassCheckRequirementFactory,
    BypassOptionFactory,
    ObstaclePropertyFactory,
)
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


class BypassCapabilityRequirementModelTest(TestCase):
    """Tests for BypassCapabilityRequirement model."""

    def test_create_requirement(self) -> None:
        bypass = BypassOptionFactory(name="Fly Over")
        flight = CapabilityTypeFactory(name="flight")
        req = BypassCapabilityRequirementFactory(
            bypass_option=bypass,
            capability_type=flight,
            minimum_value=1,
        )
        assert req.bypass_option == bypass
        assert req.capability_type == flight
        assert req.minimum_value == 1
        assert str(req) == "Fly Over requires flight >= 1"

    def test_multiple_requirements_on_one_bypass(self) -> None:
        bypass = BypassOptionFactory(name="Flirt in Draconic")
        draconic = CapabilityTypeFactory(name="ancient_draconic")
        flirting = CapabilityTypeFactory(name="flirting")
        BypassCapabilityRequirementFactory(
            bypass_option=bypass,
            capability_type=draconic,
            minimum_value=1,
        )
        BypassCapabilityRequirementFactory(
            bypass_option=bypass,
            capability_type=flirting,
            minimum_value=5,
        )
        assert bypass.capability_requirements.count() == 2

    def test_unique_capability_per_bypass(self) -> None:
        bypass = BypassOptionFactory()
        flight = CapabilityTypeFactory(name="flight")
        BypassCapabilityRequirementFactory(bypass_option=bypass, capability_type=flight)
        with self.assertRaises(IntegrityError):
            BypassCapabilityRequirementFactory(bypass_option=bypass, capability_type=flight)


class BypassCheckRequirementModelTest(TestCase):
    """Tests for BypassCheckRequirement model."""

    def test_create_check_requirement(self) -> None:
        bypass = BypassOptionFactory(name="Swim Across")
        athletics = CheckTypeFactory(name="Athletics")
        check_req = BypassCheckRequirementFactory(
            bypass_option=bypass,
            check_type=athletics,
            base_target_difficulty=25,
        )
        assert check_req.bypass_option == bypass
        assert check_req.check_type == athletics
        assert check_req.base_target_difficulty == 25

    def test_one_check_per_bypass(self) -> None:
        bypass = BypassOptionFactory()
        BypassCheckRequirementFactory(bypass_option=bypass)
        with self.assertRaises(IntegrityError):
            BypassCheckRequirementFactory(bypass_option=bypass)

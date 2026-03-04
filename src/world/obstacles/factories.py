"""Factories for obstacle system tests."""

import factory
from factory.django import DjangoModelFactory

from world.obstacles.constants import DiscoveryType, ResolutionType
from world.obstacles.models import BypassOption, ObstacleProperty


class ObstaclePropertyFactory(DjangoModelFactory):
    """Factory for ObstacleProperty."""

    class Meta:
        model = ObstacleProperty
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"property-{n}")
    description = "Test property"


class BypassOptionFactory(DjangoModelFactory):
    """Factory for BypassOption."""

    class Meta:
        model = BypassOption

    obstacle_property = factory.SubFactory(ObstaclePropertyFactory)
    name = factory.Sequence(lambda n: f"Bypass {n}")
    description_template = "Test bypass"
    discovery_type = DiscoveryType.OBVIOUS
    resolution_type = ResolutionType.PERSONAL

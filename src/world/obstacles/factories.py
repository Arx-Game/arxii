"""Factories for obstacle system tests."""

import factory
from factory.django import DjangoModelFactory

from evennia_extensions.factories import ObjectDBFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import CapabilityTypeFactory
from world.obstacles.constants import DiscoveryType, ResolutionType
from world.obstacles.models import (
    BypassCapabilityRequirement,
    BypassCheckRequirement,
    BypassOption,
    ObstacleInstance,
    ObstacleProperty,
    ObstacleTemplate,
)


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


class BypassCapabilityRequirementFactory(DjangoModelFactory):
    """Factory for BypassCapabilityRequirement."""

    class Meta:
        model = BypassCapabilityRequirement

    bypass_option = factory.SubFactory(BypassOptionFactory)
    capability_type = factory.SubFactory(CapabilityTypeFactory)
    minimum_value = 1


class BypassCheckRequirementFactory(DjangoModelFactory):
    """Factory for BypassCheckRequirement."""

    class Meta:
        model = BypassCheckRequirement

    bypass_option = factory.SubFactory(BypassOptionFactory)
    check_type = factory.SubFactory(CheckTypeFactory)
    base_target_difficulty = 25


class ObstacleTemplateFactory(DjangoModelFactory):
    """Factory for ObstacleTemplate."""

    class Meta:
        model = ObstacleTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Obstacle Template {n}")
    description_template = "A test obstacle."
    severity = 1
    blocked_capability = factory.SubFactory(CapabilityTypeFactory)


class ObstacleInstanceFactory(DjangoModelFactory):
    """Factory for ObstacleInstance."""

    class Meta:
        model = ObstacleInstance

    template = factory.SubFactory(ObstacleTemplateFactory)
    target = factory.SubFactory(ObjectDBFactory)
    template_variables = factory.LazyFunction(dict)
    is_active = True

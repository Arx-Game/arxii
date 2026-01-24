"""Factory classes for action points models."""

import factory
from factory.django import DjangoModelFactory

from world.action_points.models import ActionPointConfig, ActionPointPool


class ActionPointConfigFactory(DjangoModelFactory):
    """Factory for creating ActionPointConfig instances."""

    class Meta:
        model = ActionPointConfig
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Config {n}")
    default_maximum = 200
    daily_regen = 5
    weekly_regen = 100
    is_active = True


class ActionPointPoolFactory(DjangoModelFactory):
    """Factory for creating ActionPointPool instances."""

    class Meta:
        model = ActionPointPool

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    current = 200
    maximum = 200
    banked = 0

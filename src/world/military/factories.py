"""Factory definitions for the military system tests."""

from __future__ import annotations

import factory
import factory.django as factory_django

from world.battles.constants import DEFAULT_MORALE, UnitQuality
from world.military.models import Army, MilitaryUnit


class MilitaryUnitFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = MilitaryUnit

    name = factory.Sequence(lambda n: f"Military Unit {n}")
    descriptor = "test"
    quality = UnitQuality.TRAINED
    strength = 100
    morale = DEFAULT_MORALE


class ArmyFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Army

    name = factory.Sequence(lambda n: f"Army {n}")

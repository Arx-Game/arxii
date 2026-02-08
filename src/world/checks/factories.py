"""FactoryBoy factories for check system tests."""

from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from world.checks.models import CheckCategory, CheckType, CheckTypeTrait


class CheckCategoryFactory(DjangoModelFactory):
    class Meta:
        model = CheckCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"CheckCategory{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class CheckTypeFactory(DjangoModelFactory):
    class Meta:
        model = CheckType
        django_get_or_create = ("name", "category")

    name = factory.Sequence(lambda n: f"CheckType{n}")
    category = factory.SubFactory(CheckCategoryFactory)
    description = factory.Faker("sentence")
    is_active = True
    display_order = factory.Sequence(lambda n: n)


class CheckTypeTraitFactory(DjangoModelFactory):
    class Meta:
        model = CheckTypeTrait

    check_type = factory.SubFactory(CheckTypeFactory)
    trait = None  # Must be provided by caller
    weight = Decimal("1.0")

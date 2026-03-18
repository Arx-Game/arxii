"""FactoryBoy factories for item test data."""

import factory

from world.items.models import InteractionType, QualityTier


class QualityTierFactory(factory.django.DjangoModelFactory):
    """Factory for QualityTier."""

    class Meta:
        model = QualityTier
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Quality Tier {n}")
    color_hex = "#FFFFFF"
    numeric_min = 0
    numeric_max = 100
    stat_multiplier = 1.0
    sort_order = factory.Sequence(lambda n: n)


class InteractionTypeFactory(factory.django.DjangoModelFactory):
    """Factory for InteractionType."""

    class Meta:
        model = InteractionType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"interaction_{n}")
    label = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    description = ""

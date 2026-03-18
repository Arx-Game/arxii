"""FactoryBoy factories for item test data."""

import factory

from world.items.models import InteractionType, ItemInstance, ItemTemplate, QualityTier


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


class ItemTemplateFactory(factory.django.DjangoModelFactory):
    """Factory for ItemTemplate."""

    class Meta:
        model = ItemTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Item Template {n}")
    description = factory.LazyAttribute(lambda o: f"A {o.name}.")
    weight = 1.0
    size = 1
    value = 0
    is_active = True


class ItemInstanceFactory(factory.django.DjangoModelFactory):
    """Factory for ItemInstance."""

    class Meta:
        model = ItemInstance

    template = factory.SubFactory(ItemTemplateFactory)
    custom_name = ""
    custom_description = ""
    quantity = 1

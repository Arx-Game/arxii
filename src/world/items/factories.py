"""FactoryBoy factories for item test data."""

import factory

from world.items.constants import BodyRegion, EquipmentLayer
from world.items.models import (
    EquippedItem,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemTemplate,
    QualityTier,
    TemplateSlot,
)


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


class TemplateSlotFactory(factory.django.DjangoModelFactory):
    """Factory for TemplateSlot.

    Caller should pass ``template`` explicitly; body_region and equipment_layer
    default to TORSO/BASE for convenience.
    """

    class Meta:
        model = TemplateSlot
        django_get_or_create = ("template", "body_region", "equipment_layer")

    template = factory.SubFactory(ItemTemplateFactory)
    body_region = BodyRegion.TORSO
    equipment_layer = EquipmentLayer.BASE
    covers_lower_layers = False


class ItemFacetFactory(factory.django.DjangoModelFactory):
    """Factory for ItemFacet."""

    class Meta:
        model = ItemFacet
        django_get_or_create = ("item_instance", "facet")

    item_instance = factory.SubFactory(ItemInstanceFactory)
    facet = factory.SubFactory("world.magic.factories.FacetFactory")
    attachment_quality_tier = factory.SubFactory(QualityTierFactory)


class EquippedItemFactory(factory.django.DjangoModelFactory):
    """Factory for EquippedItem.

    Caller must pass ``character`` (an ObjectDB / Character instance) explicitly;
    there is no safe default since EquippedItem.character is a FK to ObjectDB and
    the available character-creation helpers are outside this app.
    """

    class Meta:
        model = EquippedItem
        django_get_or_create = ("character", "body_region", "equipment_layer")

    item_instance = factory.SubFactory(ItemInstanceFactory)
    body_region = BodyRegion.TORSO
    equipment_layer = EquipmentLayer.BASE
    # character — caller must provide; no default

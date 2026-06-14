"""FactoryBoy factories for item test data."""

import factory

from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.models import (
    EquippedItem,
    FashionStyle,
    FashionStyleBonus,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemTemplate,
    Mantle,
    MantleLevelClearance,
    MantleLevelDefinition,
    Outfit,
    OutfitSlot,
    QualityTier,
    TemplateSlot,
)
from world.mechanics.factories import ModifierTargetFactory


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

    class Params:
        weapon = factory.Trait(
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
            base_weapon_damage=5,
            max_durability=30,
        )
        armor = factory.Trait(
            gear_archetype=GearArchetype.LIGHT_ARMOR,
            base_armor_soak=3,
            max_durability=30,
        )


class ItemInstanceFactory(factory.django.DjangoModelFactory):
    """Factory for ItemInstance."""

    class Meta:
        model = ItemInstance

    template = factory.SubFactory(ItemTemplateFactory)
    custom_name = ""
    custom_description = ""
    quantity = 1
    durability = None


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


class OutfitFactory(factory.django.DjangoModelFactory):
    """Factory for Outfit. character_sheet and wardrobe must be provided by the caller."""

    class Meta:
        model = Outfit

    name = factory.Sequence(lambda n: f"Outfit {n}")
    description = ""


class OutfitSlotFactory(factory.django.DjangoModelFactory):
    """Factory for OutfitSlot. All fields must be provided by the caller."""

    class Meta:
        model = OutfitSlot


class FashionStyleFactory(factory.django.DjangoModelFactory):
    """Factory for FashionStyle."""

    class Meta:
        model = FashionStyle
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Fashion Style {n}")
    description = ""


class FashionStyleBonusFactory(factory.django.DjangoModelFactory):
    """Factory for FashionStyleBonus."""

    class Meta:
        model = FashionStyleBonus

    fashion_style = factory.SubFactory(FashionStyleFactory)
    target = factory.SubFactory(ModifierTargetFactory)
    weight = 1


class MantleFactory(factory.django.DjangoModelFactory):
    """Factory for Mantle."""

    class Meta:
        model = Mantle
        django_get_or_create = ("name",)

    item_instance = factory.SubFactory(ItemInstanceFactory)
    name = factory.Sequence(lambda n: f"Mantle {n}")
    description = ""
    is_active = True
    max_level = 5


class MantleLevelDefinitionFactory(factory.django.DjangoModelFactory):
    """Factory for MantleLevelDefinition."""

    class Meta:
        model = MantleLevelDefinition
        django_get_or_create = ("mantle", "level")

    mantle = factory.SubFactory(MantleFactory)
    level = factory.Sequence(lambda n: n + 1)
    codex_entry_required = factory.SubFactory("world.codex.factories.CodexEntryFactory")
    unlock_description = ""


class MantleLevelClearanceFactory(factory.django.DjangoModelFactory):
    """Factory for MantleLevelClearance."""

    class Meta:
        model = MantleLevelClearance
        django_get_or_create = ("character_sheet", "mantle", "level")

    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    mantle = factory.SubFactory(MantleFactory)
    level = 1

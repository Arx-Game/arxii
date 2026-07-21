"""FactoryBoy factories for item test data."""

from decimal import Decimal

import factory

from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.crafting.constants import CostConsumption, CraftingRecipeKind
from world.items.gems.constants import GemAxis
from world.items.models import (
    EquippedItem,
    FacetVogueMomentum,
    FashionPresentation,
    FashionStyle,
    FashionStyleBonus,
    GarmentMitigation,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemStyle,
    ItemTemplate,
    ItemTemplateProperty,
    Mantle,
    MantleLevelClearance,
    MantleLevelDefinition,
    Outfit,
    OutfitSlot,
    QualityTier,
    Style,
    TemplateSlot,
    Trendsetter,
)
from world.mechanics.factories import ModifierTargetFactory, PropertyFactory

# SubFactory import path, extracted to satisfy S1192.
_SOCIETY_FACTORY = "world.societies.factories.SocietyFactory"
_CHARACTER_SHEET_FACTORY = "world.character_sheets.factories.CharacterSheetFactory"


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


class MaterialCategoryFactory(factory.django.DjangoModelFactory):
    """Factory for MaterialCategory."""

    class Meta:
        model = "items.MaterialCategory"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Material Category {n}")
    description = ""
    sort_order = factory.Sequence(lambda n: n)


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
    material_category = None
    tied_resonance = None
    resonance_tier = None

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


class ItemTemplatePropertyFactory(factory.django.DjangoModelFactory):
    """Factory for ItemTemplateProperty."""

    class Meta:
        model = ItemTemplateProperty
        django_get_or_create = ("item_template", "property")

    item_template = factory.SubFactory(ItemTemplateFactory)
    property = factory.SubFactory(PropertyFactory)
    value = 1


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


class StyleFactory(factory.django.DjangoModelFactory):
    """Factory for Style (aesthetic vocabulary, #546)."""

    class Meta:
        model = Style
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Style {n}")
    description = ""


class ItemStyleFactory(factory.django.DjangoModelFactory):
    """Factory for ItemStyle (#546)."""

    class Meta:
        model = ItemStyle
        django_get_or_create = ("item_instance", "style")

    item_instance = factory.SubFactory(ItemInstanceFactory)
    style = factory.SubFactory(StyleFactory)
    attachment_quality_tier = factory.SubFactory(QualityTierFactory)


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

    character_sheet = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
    mantle = factory.SubFactory(MantleFactory)
    level = 1


class FacetVogueMomentumFactory(factory.django.DjangoModelFactory):
    """Factory for FacetVogueMomentum (#514)."""

    class Meta:
        model = FacetVogueMomentum

    society = factory.SubFactory(_SOCIETY_FACTORY)
    facet = factory.SubFactory("world.magic.factories.FacetFactory")
    points = 0


class FashionPresentationFactory(factory.django.DjangoModelFactory):
    """Factory for FashionPresentation (#514).

    Builds a complete presentation row suitable for integration tests and seed data.
    ``outfit`` is nullable and defaults to None — the check reads equipped items, not the FK.
    """

    class Meta:
        model = FashionPresentation

    event = factory.SubFactory("world.events.factories.EventFactory")
    presenter = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
    outfit = None
    perceiving_society = factory.SubFactory(_SOCIETY_FACTORY)
    base_score = 0
    acclaim = 0


class TrendsetterFactory(factory.django.DjangoModelFactory):
    """Factory for Trendsetter (#514)."""

    class Meta:
        model = Trendsetter

    society = factory.SubFactory(_SOCIETY_FACTORY)
    persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    fashion_style = factory.SubFactory(FashionStyleFactory)


def wire_enchanting_crafting(*, base_difficulty: int = 0):
    """Author the Enchanting skill + crafting CheckType + both crafting recipes.

    FactoryBoy chain doubling as integration-test setUp and seed data. Creates:

    * the Enchanting skill ``Trait`` + ``CheckType`` + ``CheckTypeTrait`` weight,
    * a ``CraftingRecipe`` for each of FACET_ATTACH and STYLE_ATTACH wired to that
      check + trait,
    * a small ``CraftingSkillCap`` ladder per recipe (so quality clamps have data),
    * a couple of ``CraftingRecipeConsequence`` rows across outcome bands.

    Idempotent: keyed on ``CraftingRecipe.kind`` via ``update_or_create`` so re-runs
    refresh ``base_difficulty``/``check_type`` rather than silently keeping the
    original row.

    Returns:
        The FACET_ATTACH ``CraftingRecipe`` (the primary facet-crafting recipe).
    """
    from world.checks.factories import (
        CheckTypeFactory,
        CheckTypeTraitFactory,
        ConsequenceFactory,
    )
    from world.items.crafting.models import CraftingRecipe
    from world.traits.factories import CheckOutcomeFactory, TraitFactory
    from world.traits.models import TraitCategory, TraitType

    enchanting = TraitFactory(
        name="Enchanting", trait_type=TraitType.SKILL, category=TraitCategory.CRAFTING
    )
    check_type = CheckTypeFactory(name="Enchanting")
    CheckTypeTraitFactory(check_type=check_type, trait=enchanting, weight=Decimal("1.0"))

    # Quality tiers used to seed the skill-cap ladder. Idempotent on name.
    common = QualityTierFactory(name="Common", numeric_min=0, numeric_max=29, sort_order=0)
    fine = QualityTierFactory(name="Fine", numeric_min=30, numeric_max=69, sort_order=1)
    master = QualityTierFactory(name="Masterwork", numeric_min=70, numeric_max=9999, sort_order=2)

    # Outcome bands for the consequence pool. Idempotent on name.
    success_tier = CheckOutcomeFactory(name="Enchanting Success", success_level=2)
    botch_tier = CheckOutcomeFactory(name="Enchanting Botch", success_level=-2)

    facet_recipe, _ = CraftingRecipe.objects.update_or_create(
        kind=CraftingRecipeKind.FACET_ATTACH,
        defaults={
            "name": "Attach Facet (Enchanting)",
            "check_type": check_type,
            "skill_trait": enchanting,
            "base_difficulty": base_difficulty,
            "success_level_step": 10,
            "min_success_level": 1,
        },
    )
    style_recipe, _ = CraftingRecipe.objects.update_or_create(
        kind=CraftingRecipeKind.STYLE_ATTACH,
        defaults={
            "name": "Attach Style (Enchanting)",
            "check_type": check_type,
            "skill_trait": enchanting,
            "base_difficulty": base_difficulty,
            "success_level_step": 10,
            "min_success_level": 1,
        },
    )

    for recipe in (facet_recipe, style_recipe):
        _wire_recipe_caps_and_consequences(
            recipe=recipe,
            tiers=(common, fine, master),
            success_tier=success_tier,
            botch_tier=botch_tier,
            consequence_factory=ConsequenceFactory,
        )

    # Seed an ITEM_CREATE recipe producing a simple craftable dagger.
    craftable_template = ItemTemplateFactory(name="Craftable Dagger", is_craftable=True)
    create_recipe, _ = CraftingRecipe.objects.update_or_create(
        kind=CraftingRecipeKind.ITEM_CREATE,
        output_item_template=craftable_template,
        defaults={
            "name": "Create Item (Enchanting)",
            "check_type": check_type,
            "skill_trait": enchanting,
            "base_difficulty": base_difficulty,
            "success_level_step": 10,
            "min_success_level": 1,
        },
    )
    _wire_recipe_caps_and_consequences(
        recipe=create_recipe,
        tiers=(common, fine, master),
        success_tier=success_tier,
        botch_tier=botch_tier,
        consequence_factory=ConsequenceFactory,
    )

    return facet_recipe


def _wire_recipe_caps_and_consequences(
    *, recipe, tiers, success_tier, botch_tier, consequence_factory
) -> None:
    """Seed a skill-cap ladder + a consequence pool for ``recipe`` (idempotent)."""
    from world.checks.models import Consequence
    from world.items.crafting.models import CraftingRecipeConsequence, CraftingSkillCap

    common, fine, master = tiers
    ladder = [(0, common), (40, fine), (80, master)]
    for min_skill, tier in ladder:
        CraftingSkillCap.objects.update_or_create(
            recipe=recipe,
            min_skill_value=min_skill,
            defaults={"max_quality_tier": tier},
        )

    # A consequence per band so integration tests have authored pool rows. Use a
    # stable label per (recipe, tier) so re-runs reuse the same Consequence row.
    for tier_outcome, consumption, label in (
        (success_tier, CostConsumption.FULL, f"{recipe.name}: clean success"),
        (botch_tier, CostConsumption.PARTIAL, f"{recipe.name}: botched attempt"),
    ):
        consequence = Consequence.objects.filter(label=label).first()
        if consequence is None:
            consequence = consequence_factory(outcome_tier=tier_outcome, label=label)
        CraftingRecipeConsequence.objects.update_or_create(
            recipe=recipe,
            consequence=consequence,
            defaults={"cost_consumption": consumption},
        )


def install_full_lab_station(room_profile, *, level: int = 1):
    """Install a full-durability Lab station in ``room_profile`` (#1234).

    Test-fixture helper: creates the ``RoomFeatureInstance`` (LAB strategy) +
    a full-durability ``LabStationDetails`` in one call. Crafting-pipeline
    tests need a live station in the crafter's room now that
    ``CraftingRecipe.requires_station`` defaults to ``True`` (Task 6) — callers
    must still set the crafter character's ``.location`` to
    ``room_profile.objectdb`` themselves before crafting.

    Returns the created ``LabStationDetails``.
    """
    from world.items.crafting.constants import LAB_BASE_DURABILITY_PER_LEVEL
    from world.items.crafting.models import LabStationDetails
    from world.room_features.constants import RoomFeatureServiceStrategy
    from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory

    kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
    instance = RoomFeatureInstanceFactory(room_profile=room_profile, feature_kind=kind, level=level)
    max_durability = LAB_BASE_DURABILITY_PER_LEVEL * level
    return LabStationDetails.objects.create(
        feature_instance=instance,
        durability=max_durability,
        max_durability=max_durability,
    )


class CraftingRecipeFactory(factory.django.DjangoModelFactory):
    """Factory for CraftingRecipe.

    Creates a minimal recipe with sensible defaults. The composite unique
    constraint is ``(kind, output_item_template)``, so the factory keys
    ``django_get_or_create`` on both — two bare ``CraftingRecipeFactory()``
    calls return the *same* FACET_ATTACH recipe (null output) instead of
    raising ``IntegrityError`` on the second. Override ``kind`` (and
    ``output_item_template`` for ITEM_CREATE) to create a different recipe.
    """

    class Meta:
        model = "items.CraftingRecipe"
        django_get_or_create = ("kind", "output_item_template")

    name = factory.Sequence(lambda n: f"Crafting Recipe {n}")
    kind = CraftingRecipeKind.FACET_ATTACH
    output_item_template = None
    base_difficulty = 0
    success_level_step = 10
    min_success_level = 1
    action_point_cost = 0
    anima_cost = 0


class CraftingMaterialRequirementFactory(factory.django.DjangoModelFactory):
    """Factory for CraftingMaterialRequirement.

    Defaults to a single unit of a freshly generated item template with no minimum
    quality requirement. Pass ``min_quality_tier`` explicitly when tier gating is needed.
    """

    class Meta:
        model = "items.CraftingMaterialRequirement"

    recipe = factory.SubFactory(CraftingRecipeFactory)
    item_template = factory.SubFactory(ItemTemplateFactory)
    quantity = 1
    min_quality_tier = None


class CraftingSkillCapFactory(factory.django.DjangoModelFactory):
    """Factory for CraftingSkillCap.

    Requires ``recipe`` and ``max_quality_tier`` to be passed explicitly when
    building multi-band fixtures; the defaults give sensible standalone rows.
    The unique constraint on (recipe, min_skill_value) means callers must vary
    min_skill_value when adding multiple caps to the same recipe.
    """

    class Meta:
        model = "items.CraftingSkillCap"

    recipe = factory.SubFactory(CraftingRecipeFactory)
    min_skill_value = 0
    max_quality_tier = factory.SubFactory(QualityTierFactory)


class CraftingRecipeConsequenceFactory(factory.django.DjangoModelFactory):
    """Factory for CraftingRecipeConsequence.

    The unique constraint on (recipe, consequence) means callers must use distinct
    combinations; by default both are freshly generated to avoid collisions.
    """

    class Meta:
        model = "items.CraftingRecipeConsequence"

    recipe = factory.SubFactory(CraftingRecipeFactory)
    consequence = factory.SubFactory("world.checks.factories.ConsequenceFactory")
    weight_override = None
    cost_consumption = CostConsumption.FULL


class CraftingRecipeModifierFactory(factory.django.DjangoModelFactory):
    """Factory for CraftingRecipeModifier.

    The unique constraint on (recipe, target) means callers must use distinct
    targets when adding multiple modifier outcomes to the same recipe.
    """

    class Meta:
        model = "items.CraftingRecipeModifier"

    recipe = factory.SubFactory(CraftingRecipeFactory)
    target = factory.SubFactory(ModifierTargetFactory)
    base_value = 0
    quality_scale_factor = 0


class CraftedItemRecipeFactory(factory.django.DjangoModelFactory):
    """Factory for CraftedItemRecipe — a recipe applied to an item at a quality tier."""

    class Meta:
        model = "items.CraftedItemRecipe"

    item_instance = factory.SubFactory(ItemInstanceFactory)
    recipe = factory.SubFactory(CraftingRecipeFactory)
    quality_tier = factory.SubFactory(QualityTierFactory)


class GarmentMitigationFactory(factory.django.DjangoModelFactory):
    """Factory for GarmentMitigation. ``stat_key``/``value`` default to a wool-coat-style COLD."""

    class Meta:
        model = GarmentMitigation

    item_template = factory.SubFactory(ItemTemplateFactory)
    stat_key = "cold"
    value = 30
    resonance = None


class GemGradeFactory(factory.django.DjangoModelFactory):
    """Factory for GemGrade — one grade on one gem axis (word + multiplier)."""

    class Meta:
        model = "items.GemGrade"
        django_get_or_create = ("axis", "label")

    axis = GemAxis.SIZE
    sort_order = factory.Sequence(lambda n: n)
    label = factory.Sequence(lambda n: f"grade-{n}")
    multiplier = Decimal("1.0")


class GemDetailsFactory(factory.django.DjangoModelFactory):
    """Factory for GemDetails — marks a template as a gem type at a quality level."""

    class Meta:
        model = "items.GemDetails"

    item_template = factory.SubFactory(ItemTemplateFactory)
    quality_level = 1


class GemInstanceDetailsFactory(factory.django.DjangoModelFactory):
    """Factory for GemInstanceDetails — a cut/graded gem instance's three axes."""

    class Meta:
        model = "items.GemInstanceDetails"

    item_instance = factory.SubFactory(ItemInstanceFactory)
    size_grade = factory.SubFactory(GemGradeFactory, axis=GemAxis.SIZE)
    purity_grade = factory.SubFactory(GemGradeFactory, axis=GemAxis.PURITY)
    cut_grade = factory.SubFactory(GemGradeFactory, axis=GemAxis.CUT)


class AdornmentFactory(factory.django.DjangoModelFactory):
    """Factory for Adornment — a gem set into a host item. Pass a gem instance for
    ``gem_instance`` when exercising adorn_item; the default is a plain instance."""

    class Meta:
        model = "items.Adornment"

    host_instance = factory.SubFactory(ItemInstanceFactory)
    gem_instance = factory.SubFactory(ItemInstanceFactory)
    narration = ""


class CommonGemBucketFactory(factory.django.DjangoModelFactory):
    """Factory for CommonGemBucket — a crafter's per-tier common-gem value stock."""

    class Meta:
        model = "items.CommonGemBucket"
        django_get_or_create = ("character_sheet", "tier")

    character_sheet = factory.SubFactory(_CHARACTER_SHEET_FACTORY)
    tier = factory.SubFactory(MaterialCategoryFactory)
    value = 0

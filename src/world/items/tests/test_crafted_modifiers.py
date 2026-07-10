"""Tests for per-instance crafted item modifiers (#1567)."""

from decimal import Decimal

from django.test import TestCase

from world.items.crafting.constants import CraftingRecipeKind
from world.items.crafting.models import CraftedItemRecipe, CraftingRecipeModifier
from world.items.factories import (
    CraftedItemRecipeFactory,
    CraftingRecipeFactory,
    CraftingRecipeModifierFactory,
    ItemInstanceFactory,
    QualityTierFactory,
)
from world.mechanics.factories import ModifierTargetFactory


def _populate_caches(item):
    """Populate the prefetch attributes that CharacterEquipmentHandler would set."""
    crafted_recipes = list(
        CraftedItemRecipe.objects.filter(item_instance=item).select_related(
            "recipe", "quality_tier"
        )
    )
    for crafted in crafted_recipes:
        crafted.recipe.cached_modifier_outcomes = list(
            CraftingRecipeModifier.objects.filter(recipe=crafted.recipe).select_related("target")
        )
    item.cached_crafted_recipes = crafted_recipes


class CraftedModifierValueTests(TestCase):
    """ItemInstance.crafted_modifier_value computes base + quality scaling."""

    def test_no_crafted_recipes_returns_zero(self) -> None:
        item = ItemInstanceFactory()
        target = ModifierTargetFactory()
        item.cached_crafted_recipes = []
        self.assertEqual(item.crafted_modifier_value(target), 0)

    def test_single_outcome_base_value_only(self) -> None:
        target = ModifierTargetFactory()
        item = ItemInstanceFactory()
        quality = QualityTierFactory(stat_multiplier=Decimal("1.00"))
        crafted = CraftedItemRecipeFactory(
            item_instance=item,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=crafted.recipe,
            target=target,
            base_value=5,
            quality_scale_factor=0,
        )
        _populate_caches(item)
        self.assertEqual(item.crafted_modifier_value(target), 5)

    def test_base_plus_quality_scaling(self) -> None:
        target = ModifierTargetFactory()
        item = ItemInstanceFactory()
        quality = QualityTierFactory(stat_multiplier=Decimal("1.20"))
        crafted = CraftedItemRecipeFactory(
            item_instance=item,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=crafted.recipe,
            target=target,
            base_value=3,
            quality_scale_factor=5,
        )
        _populate_caches(item)
        # 3 + round(5 * 1.20) = 3 + 6 = 9
        self.assertEqual(item.crafted_modifier_value(target), 9)

    def test_multiple_recipes_same_target_stack(self) -> None:
        target = ModifierTargetFactory()
        item = ItemInstanceFactory()
        quality = QualityTierFactory(stat_multiplier=Decimal("1.00"))
        # Each CraftedItemRecipeFactory creates its own CraftingRecipe (via
        # SubFactory with django_get_or_create on kind), so we need distinct
        # recipe kinds to avoid the unique constraint on (item, recipe).
        recipe1 = CraftingRecipeFactory(kind=CraftingRecipeKind.FACET_ATTACH)
        recipe2 = CraftingRecipeFactory(kind=CraftingRecipeKind.STYLE_ATTACH)
        CraftedItemRecipeFactory(
            item_instance=item,
            recipe=recipe1,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=recipe1,
            target=target,
            base_value=4,
            quality_scale_factor=0,
        )
        CraftedItemRecipeFactory(
            item_instance=item,
            recipe=recipe2,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=recipe2,
            target=target,
            base_value=6,
            quality_scale_factor=0,
        )
        _populate_caches(item)
        self.assertEqual(item.crafted_modifier_value(target), 10)

    def test_non_matching_target_excluded(self) -> None:
        target_a = ModifierTargetFactory()
        target_b = ModifierTargetFactory()
        item = ItemInstanceFactory()
        quality = QualityTierFactory(stat_multiplier=Decimal("1.00"))
        crafted = CraftedItemRecipeFactory(
            item_instance=item,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=crafted.recipe,
            target=target_a,
            base_value=5,
            quality_scale_factor=0,
        )
        _populate_caches(item)
        self.assertEqual(item.crafted_modifier_value(target_b), 0)

    def test_zero_value_outcome_produces_no_contribution(self) -> None:
        target = ModifierTargetFactory()
        item = ItemInstanceFactory()
        quality = QualityTierFactory(stat_multiplier=Decimal("1.00"))
        crafted = CraftedItemRecipeFactory(
            item_instance=item,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=crafted.recipe,
            target=target,
            base_value=0,
            quality_scale_factor=0,
        )
        _populate_caches(item)
        self.assertEqual(item.crafted_modifier_value(target), 0)


class CraftedModifierHandlerTests(TestCase):
    """CharacterEquipmentHandler.crafted_modifier_total aggregates equipped items."""

    def test_no_equipped_items_returns_zero(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory

        character = CharacterFactory(db_key="CraftedModHandlerChar")
        CharacterSheetFactory(character=character)
        target = ModifierTargetFactory()
        self.assertEqual(character.equipped_items.crafted_modifier_total(target), 0)

    def test_equipped_item_crafted_mod_aggregated(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory

        character = CharacterFactory(db_key="CraftedModHandlerChar2")
        CharacterSheetFactory(character=character)
        target = ModifierTargetFactory()
        quality = QualityTierFactory(stat_multiplier=Decimal("1.20"))
        item = ItemInstanceFactory()
        crafted = CraftedItemRecipeFactory(
            item_instance=item,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=crafted.recipe,
            target=target,
            base_value=3,
            quality_scale_factor=5,
        )
        EquippedItemFactory(
            character=character,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        # 3 + round(5 * 1.20) = 9
        self.assertEqual(character.equipped_items.crafted_modifier_total(target), 9)
        character.equipped_items.invalidate()


class CraftedModifierInChecksTests(TestCase):
    """collect_check_modifiers includes crafted modifiers for equipped items."""

    def test_crafted_mod_appears_in_check_breakdown(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.checks.factories import CheckTypeFactory
        from world.checks.services import collect_check_modifiers
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.mechanics.models import ModifierCategory, ModifierTarget

        character = CharacterFactory(db_key="CraftedCheckChar")
        sheet = CharacterSheetFactory(character=character)

        # Create a ModifierTarget linked to a CheckType via target_check_type
        # so _character_and_equipment_contributions resolves scoped_target.
        category = ModifierCategory.objects.create(name="check_1567", display_order=99)
        target = ModifierTarget.objects.create(
            name="crafted_check_target",
            category=category,
        )
        check_type = CheckTypeFactory(name="crafted_check_type_1567")
        target.target_check_type = check_type
        target.save()

        quality = QualityTierFactory(stat_multiplier=Decimal("1.20"))
        item = ItemInstanceFactory()
        crafted = CraftedItemRecipeFactory(
            item_instance=item,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=crafted.recipe,
            target=target,
            base_value=3,
            quality_scale_factor=5,
        )
        EquippedItemFactory(
            character=character,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        breakdown = collect_check_modifiers(sheet, check_type)
        crafted_contribs = [
            c
            for c in breakdown.contributions
            if c.source_kind == "equipment" and c.source_label == "Crafted modifiers"
        ]
        self.assertEqual(len(crafted_contribs), 1)
        self.assertEqual(crafted_contribs[0].value, 9)
        character.equipped_items.invalidate()


class CraftedModifierInGetModifierTotalTests(TestCase):
    """get_modifier_total includes crafted modifiers for equipped items."""

    def test_crafted_mod_in_total(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import get_modifier_total

        character = CharacterFactory(db_key="CraftedTotalChar")
        sheet = CharacterSheetFactory(character=character)

        target = ModifierTargetFactory(category=ModifierCategoryFactory(name="stat_1567"))

        quality = QualityTierFactory(stat_multiplier=Decimal("1.20"))
        item = ItemInstanceFactory()
        crafted = CraftedItemRecipeFactory(
            item_instance=item,
            quality_tier=quality,
        )
        CraftingRecipeModifierFactory(
            recipe=crafted.recipe,
            target=target,
            base_value=3,
            quality_scale_factor=5,
        )
        EquippedItemFactory(
            character=character,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # 3 + round(5 * 1.20) = 9
        self.assertEqual(get_modifier_total(sheet, target), 9)
        character.equipped_items.invalidate()


class CraftedModifierWriteTests(TestCase):
    """run_crafting_recipe records a CraftedItemRecipe on successful craft."""

    def setUp(self) -> None:
        from evennia_extensions.factories import AccountFactory, RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import (
            install_full_lab_station,
            wire_enchanting_crafting,
        )

        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character
        room_profile = RoomProfileFactory()
        self.character.location = room_profile.objectdb
        self.character.save()
        install_full_lab_station(room_profile)

    def _item(self):
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        template = ItemTemplateFactory(facet_capacity=3)
        return ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)

    def _facet(self):
        from world.magic.factories import FacetFactory

        return FacetFactory()

    def test_successful_craft_creates_crafted_item_recipe(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.services import run_crafting_recipe
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="CraftModSuccess", success_level=5)
        item = self._item()
        with force_check_outcome(success):
            result = run_crafting_recipe(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                target=self._facet(),
            )

        self.assertTrue(result.attached)
        self.assertIsNotNone(result.crafted_recipe)
        self.assertEqual(result.crafted_recipe.item_instance, item)
        self.assertEqual(result.crafted_recipe.recipe, self.recipe)
        self.assertEqual(result.crafted_recipe.quality_tier, result.quality_tier)

    def test_recrafting_updates_quality_tier_in_place(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftedItemRecipe
        from world.items.crafting.services import run_crafting_recipe
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="CraftModRecraft", success_level=5)
        item = self._item()
        with force_check_outcome(success):
            result1 = run_crafting_recipe(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                target=self._facet(),
            )
        self.assertEqual(result1.crafted_recipe.quality_tier, result1.quality_tier)

        # Re-craft — update_or_create should not create a duplicate row.
        success2 = CheckOutcomeFactory(name="CraftModRecraft2", success_level=5)
        with force_check_outcome(success2):
            run_crafting_recipe(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                target=self._facet(),
            )

        self.assertEqual(
            CraftedItemRecipe.objects.filter(item_instance=item, recipe=self.recipe).count(),
            1,
        )

    def test_failed_craft_creates_no_crafted_item_recipe(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftedItemRecipe
        from world.items.crafting.services import run_crafting_recipe
        from world.traits.factories import CheckOutcomeFactory

        botch = CheckOutcomeFactory(name="CraftModBotch", success_level=-2)
        item = self._item()
        with force_check_outcome(botch):
            result = run_crafting_recipe(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                target=self._facet(),
            )

        self.assertFalse(result.attached)
        self.assertIsNone(result.crafted_recipe)
        self.assertFalse(CraftedItemRecipe.objects.filter(item_instance=item).exists())

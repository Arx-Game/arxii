"""Tests for world.items.crafting.cost — cost staging, affordability, and fractional consumption.

TDD test suite per task-4-brief.md.  Covers:
  - Affordable path: stage_and_assert_affordable returns a correct StagedCost.
  - Insufficient AP raises CraftingCostUnaffordable.
  - Insufficient Anima raises CraftingCostUnaffordable.
  - Insufficient materials raises CraftingCostUnaffordable.
  - consume_cost NONE consumes nothing.
  - consume_cost PARTIAL consumes ceil(cost * 0.5) AP + Anima, ALL materials.
  - consume_cost FULL consumes AP, Anima, and all materials.

Test character setup mirrors world/items/tests/test_crafting.py (CharacterSheetFactory +
CharacterFactory via ActionPointPoolFactory / CharacterAnimaFactory).
"""

import math

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.action_points.factories import ActionPointPoolFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.constants import CostConsumption
from world.items.crafting.cost import StagedCost, consume_cost, stage_and_assert_affordable
from world.items.exceptions import CraftingCostUnaffordable
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    CraftingRecipeFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.magic.factories import CharacterAnimaFactory
from world.magic.models import CharacterAnima


class _CraftingCostBase(TestCase):
    """Shared set-up: a character with AP pool, Anima, and a recipe."""

    def setUp(self) -> None:
        # A character ObjectDB and its CharacterSheet (the sheet is the inventory holder).
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

        # AP pool: default 200 current. Override per test as needed.
        self.pool = ActionPointPoolFactory(character=self.character, current=200, maximum=200)

        # Anima row: default 10 current.
        self.anima = CharacterAnimaFactory(character=self.character, current=10, maximum=10)

        # A minimal recipe with no costs and no material requirements by default.
        self.recipe = CraftingRecipeFactory(action_point_cost=0, anima_cost=0)


class StageAndAssertAffordableTests(_CraftingCostBase):
    """Affordability pre-check for stage_and_assert_affordable."""

    def test_no_costs_returns_empty_staged_cost(self) -> None:
        """A recipe with zero AP, Anima, and no materials is always affordable."""
        result = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        self.assertIsInstance(result, StagedCost)
        self.assertEqual(result.action_points, 0)
        self.assertEqual(result.anima, 0)
        self.assertEqual(result.material_allocations, [])

    def test_sufficient_ap_returns_staged_cost(self) -> None:
        self.recipe.action_point_cost = 50
        self.recipe.save(update_fields=["action_point_cost"])
        self.pool.current = 100
        self.pool.save(update_fields=["current"])

        result = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        self.assertEqual(result.action_points, 50)

    def test_sufficient_anima_returns_staged_cost(self) -> None:
        self.recipe.anima_cost = 5
        self.recipe.save(update_fields=["anima_cost"])
        self.anima.current = 10
        self.anima.save(update_fields=["current"])

        result = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        self.assertEqual(result.anima, 5)

    def test_with_materials_returns_pks(self) -> None:
        template = ItemTemplateFactory()
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=template, quantity=1)
        item = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet, quantity=1)

        result = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        self.assertIn(item.pk, [inst.pk for inst, _ in result.material_allocations])

    def test_insufficient_ap_raises(self) -> None:
        self.recipe.action_point_cost = 100
        self.recipe.save(update_fields=["action_point_cost"])
        self.pool.current = 50
        self.pool.save(update_fields=["current"])

        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_insufficient_anima_raises(self) -> None:
        self.recipe.anima_cost = 20
        self.recipe.save(update_fields=["anima_cost"])
        self.anima.current = 5
        self.anima.save(update_fields=["current"])

        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_missing_anima_row_treats_as_zero(self) -> None:
        """A character with no CharacterAnima row is treated as having 0 anima."""
        # Delete the anima row created in setUp.
        CharacterAnima.objects.filter(character=self.character).delete()

        self.recipe.anima_cost = 5
        self.recipe.save(update_fields=["anima_cost"])

        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_insufficient_materials_raises(self) -> None:
        template = ItemTemplateFactory()
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=template, quantity=3)
        # Only 1 item in inventory (need 3).
        ItemInstanceFactory(template=template, holder_character_sheet=self.sheet, quantity=1)

        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_insufficient_materials_no_items_raises(self) -> None:
        template = ItemTemplateFactory()
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=template, quantity=1)
        # No items in inventory at all.

        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_quality_tier_filtering(self) -> None:
        """An item below minimum quality tier does not satisfy the requirement."""
        low_tier = QualityTierFactory(name="Common", numeric_min=0, numeric_max=29, sort_order=0)
        high_tier = QualityTierFactory(name="Fine", numeric_min=30, numeric_max=69, sort_order=1)
        template = ItemTemplateFactory()
        CraftingMaterialRequirementFactory(
            recipe=self.recipe,
            item_template=template,
            quantity=1,
            min_quality_tier=high_tier,
        )
        # Item is of the low tier — below the minimum.
        ItemInstanceFactory(
            template=template,
            holder_character_sheet=self.sheet,
            quantity=1,
            quality_tier=low_tier,
        )

        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )


class ConsumeCostNoneTests(_CraftingCostBase):
    """consume_cost with NONE consumes nothing."""

    def test_none_consumes_nothing(self) -> None:
        template = ItemTemplateFactory()
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=template, quantity=1)
        item = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet, quantity=1)
        staged = StagedCost(action_points=30, anima=5, material_allocations=[(item, 1)])

        result = consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.NONE,
        )

        self.assertEqual(
            result, {"action_points": 0, "anima": 0, "materials": 0, "common_gem_value": 0}
        )
        # AP pool unchanged.
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 200)
        # Anima unchanged.
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 10)
        # Item still exists.
        from world.items.models import ItemInstance

        self.assertTrue(ItemInstance.objects.filter(pk=item.pk).exists())


class ConsumeCostPartialTests(_CraftingCostBase):
    """consume_cost with PARTIAL charges ceil(cost * 0.5) AP/Anima + ALL materials."""

    def test_partial_charges_ceil_half_ap_and_anima(self) -> None:
        self.pool.current = 200
        self.pool.save(update_fields=["current"])
        self.anima.current = 10
        self.anima.save(update_fields=["current"])

        # AP cost=7 → ceil(7 * 0.5) = ceil(3.5) = 4
        # Anima cost=3 → ceil(3 * 0.5) = ceil(1.5) = 2
        staged = StagedCost(action_points=7, anima=3, material_allocations=[])

        result = consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.PARTIAL,
        )

        expected_ap = math.ceil(7 * 0.5)
        expected_anima = math.ceil(3 * 0.5)
        self.assertEqual(result["action_points"], expected_ap)
        self.assertEqual(result["anima"], expected_anima)

        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 200 - expected_ap)

        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 10 - expected_anima)

    def test_partial_consumes_all_materials(self) -> None:
        template = ItemTemplateFactory()
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=template, quantity=1)
        item1 = ItemInstanceFactory(
            template=template, holder_character_sheet=self.sheet, quantity=1
        )
        item2 = ItemInstanceFactory(
            template=template, holder_character_sheet=self.sheet, quantity=1
        )
        staged = StagedCost(action_points=0, anima=0, material_allocations=[(item1, 1), (item2, 1)])

        result = consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.PARTIAL,
        )

        self.assertEqual(result["materials"], 2)
        from world.items.models import ItemInstance

        self.assertFalse(ItemInstance.objects.filter(pk__in=[item1.pk, item2.pk]).exists())

    def test_partial_zero_cost_is_zero(self) -> None:
        """PARTIAL of 0 AP/Anima should charge 0."""
        staged = StagedCost(action_points=0, anima=0, material_allocations=[])

        result = consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.PARTIAL,
        )

        self.assertEqual(result["action_points"], 0)
        self.assertEqual(result["anima"], 0)


class ConsumeCostFullTests(_CraftingCostBase):
    """consume_cost with FULL charges AP, Anima, and all materials in full."""

    def test_full_charges_full_ap_and_anima(self) -> None:
        self.pool.current = 200
        self.pool.save(update_fields=["current"])
        self.anima.current = 10
        self.anima.save(update_fields=["current"])

        staged = StagedCost(action_points=50, anima=8, material_allocations=[])

        result = consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.FULL,
        )

        self.assertEqual(result["action_points"], 50)
        self.assertEqual(result["anima"], 8)

        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 150)

        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 2)

    def test_full_consumes_all_materials(self) -> None:
        template = ItemTemplateFactory()
        item = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet, quantity=1)
        staged = StagedCost(action_points=0, anima=0, material_allocations=[(item, 1)])

        result = consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.FULL,
        )

        self.assertEqual(result["materials"], 1)
        from world.items.models import ItemInstance

        self.assertFalse(ItemInstance.objects.filter(pk=item.pk).exists())

    def test_full_returns_summary_dict(self) -> None:
        template = ItemTemplateFactory()
        item = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet, quantity=1)
        staged = StagedCost(action_points=10, anima=3, material_allocations=[(item, 1)])

        result = consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.FULL,
        )

        self.assertIn("action_points", result)
        self.assertIn("anima", result)
        self.assertIn("materials", result)

    def test_full_zero_ap_zero_anima_no_pool_side_effects(self) -> None:
        """FULL with 0 costs leaves pool and anima unchanged."""
        self.pool.current = 200
        self.pool.save(update_fields=["current"])
        self.anima.current = 10
        self.anima.save(update_fields=["current"])

        staged = StagedCost(action_points=0, anima=0, material_allocations=[])

        consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.FULL,
        )

        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 200)
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 10)


class ConsumeCostApPoolCreationTests(_CraftingCostBase):
    """consume_cost uses get_or_create — works even if pool didn't exist beforehand."""

    def test_spend_on_auto_created_pool(self) -> None:
        # Delete the pool set up in setUp.
        ActionPointPool.objects.filter(character=self.character).delete()

        staged = StagedCost(action_points=10, anima=0, material_allocations=[])

        result = consume_cost(
            crafter_character=self.character,
            staged=staged,
            consumption=CostConsumption.FULL,
        )

        self.assertEqual(result["action_points"], 10)
        pool = ActionPointPool.objects.get(character=self.character)
        # Default created with 200 current (from ActionPointConfig default), then spent 10.
        self.assertEqual(pool.current, 190)


class ConsumeCostApShortfallTests(_CraftingCostBase):
    """consume_cost raises CraftingCostUnaffordable when AP is drained after staging."""

    def test_ap_drained_between_stage_and_consume_raises(self) -> None:
        """If the pool is emptied after staging, consume_cost raises instead of lying."""
        staged = StagedCost(action_points=50, anima=0, material_allocations=[])

        # Simulate a concurrent spend draining the pool below the staged amount.
        self.pool.current = 0
        self.pool.save(update_fields=["current"])

        with self.assertRaises(CraftingCostUnaffordable):
            consume_cost(
                crafter_character=self.character,
                staged=staged,
                consumption=CostConsumption.FULL,
            )


class ConsumeCostAnimaShortfallTests(_CraftingCostBase):
    """consume_cost raises when Anima is drained after staging — symmetric with AP (#1243)."""

    def test_anima_drained_between_stage_and_consume_raises(self) -> None:
        """A concurrent spend below the staged anima aborts instead of silently clamping.

        ``deduct_anima(lethal=False)`` would clamp to available and leave the consumed
        summary over-reporting; the symmetric guard fails hard like the AP path instead.
        """
        staged = StagedCost(action_points=0, anima=8, material_allocations=[])

        # Simulate a concurrent spend draining anima below the staged amount.
        self.anima.current = 3
        self.anima.save(update_fields=["current"])

        with self.assertRaises(CraftingCostUnaffordable):
            consume_cost(
                crafter_character=self.character,
                staged=staged,
                consumption=CostConsumption.FULL,
            )
        # The raise aborts before deduct_anima — anima is untouched (no partial clamp).
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 3)

    def test_anima_row_deleted_after_staging_raises(self) -> None:
        """A positive anima cost can't be paid when the anima row vanished after staging."""
        staged = StagedCost(action_points=0, anima=5, material_allocations=[])
        CharacterAnima.objects.filter(character=self.character).delete()

        with self.assertRaises(CraftingCostUnaffordable):
            consume_cost(
                crafter_character=self.character,
                staged=staged,
                consumption=CostConsumption.FULL,
            )

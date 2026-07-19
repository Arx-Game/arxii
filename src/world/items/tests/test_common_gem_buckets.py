"""Tests for common-gem value buckets + bulk value requirements (Build 0b slice 5)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.constants import CostConsumption
from world.items.crafting.cost import consume_cost, stage_and_assert_affordable
from world.items.exceptions import CraftingCostUnaffordable, InsufficientCommonGems
from world.items.factories import (
    CommonGemBucketFactory,
    CraftingMaterialRequirementFactory,
    CraftingRecipeFactory,
    ItemTemplateFactory,
    MaterialCategoryFactory,
)
from world.items.gems.buckets import common_gem_value, credit_common_gems, spend_common_gems


class BucketServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory(character=CharacterFactory())
        cls.tier = MaterialCategoryFactory(name="Semiprecious Gems")

    def test_value_zero_when_no_bucket(self):
        self.assertEqual(common_gem_value(self.sheet, self.tier), 0)

    def test_credit_creates_then_accumulates(self):
        credit_common_gems(self.sheet, self.tier, 100)
        self.assertEqual(common_gem_value(self.sheet, self.tier), 100)
        credit_common_gems(self.sheet, self.tier, 50)
        self.assertEqual(common_gem_value(self.sheet, self.tier), 150)

    def test_spend_decrements(self):
        credit_common_gems(self.sheet, self.tier, 100)
        spend_common_gems(self.sheet, self.tier, 30)
        self.assertEqual(common_gem_value(self.sheet, self.tier), 70)

    def test_spend_insufficient_raises_and_spends_nothing(self):
        credit_common_gems(self.sheet, self.tier, 20)
        with self.assertRaises(InsufficientCommonGems):
            spend_common_gems(self.sheet, self.tier, 50)
        self.assertEqual(common_gem_value(self.sheet, self.tier), 20)


class ValueRequirementConstraintTests(TestCase):
    def test_required_value_needs_a_category_not_a_template(self):
        recipe = CraftingRecipeFactory()
        tmpl = ItemTemplateFactory(name="Ruby")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CraftingMaterialRequirementFactory(
                recipe=recipe, item_template=tmpl, material_category=None, required_value=100
            )


class BulkValueCraftingTests(TestCase):
    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.tier = MaterialCategoryFactory(name="Semiprecious Gems")
        self.recipe = CraftingRecipeFactory(
            requires_station=False, action_point_cost=0, anima_cost=0
        )
        CraftingMaterialRequirementFactory(
            recipe=self.recipe,
            item_template=None,
            material_category=self.tier,
            required_value=100,
        )

    def test_affordable_when_bucket_covers_value(self):
        CommonGemBucketFactory(character_sheet=self.sheet, tier=self.tier, value=150)
        staged = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        self.assertEqual(staged.bucket_spends, [(self.tier, 100)])

    def test_unaffordable_when_bucket_short(self):
        CommonGemBucketFactory(character_sheet=self.sheet, tier=self.tier, value=50)
        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_consume_spends_the_bucket(self):
        CommonGemBucketFactory(character_sheet=self.sheet, tier=self.tier, value=150)
        staged = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        summary = consume_cost(
            crafter_character=self.character, staged=staged, consumption=CostConsumption.FULL
        )
        self.assertEqual(summary["common_gem_value"], 100)
        self.assertEqual(common_gem_value(self.sheet, self.tier), 50)  # 150 - 100

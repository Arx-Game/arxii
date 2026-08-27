"""Tests for material value buckets + bulk value requirements (#2540 slice 2).

Originally the gem-only "common gem bucket" tests (Build 0b slice 5); generalized
along with the models/services (see ``world.items.materials_models``).
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.constants import CostConsumption
from world.items.crafting.cost import consume_cost, stage_and_assert_affordable
from world.items.exceptions import CraftingCostUnaffordable, InsufficientMaterialStock
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    CraftingRecipeFactory,
    ItemTemplateFactory,
    MaterialBucketFactory,
    MaterialCategoryFactory,
)
from world.items.gems.buckets import credit_materials, material_value, spend_materials
from world.items.materials_models import MaterialBucket


class BucketServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory(character=CharacterFactory())
        cls.material_category = MaterialCategoryFactory(name="Semiprecious Gems")

    def test_value_zero_when_no_bucket(self):
        self.assertEqual(material_value(self.sheet, self.material_category), 0)

    def test_credit_creates_then_accumulates(self):
        credit_materials(self.sheet, self.material_category, 100)
        self.assertEqual(material_value(self.sheet, self.material_category), 100)
        credit_materials(self.sheet, self.material_category, 50)
        self.assertEqual(material_value(self.sheet, self.material_category), 150)

    def test_spend_decrements(self):
        credit_materials(self.sheet, self.material_category, 100)
        spend_materials(self.sheet, self.material_category, 30)
        self.assertEqual(material_value(self.sheet, self.material_category), 70)

    def test_spend_insufficient_raises_and_spends_nothing(self):
        credit_materials(self.sheet, self.material_category, 20)
        with self.assertRaises(InsufficientMaterialStock):
            spend_materials(self.sheet, self.material_category, 50)
        self.assertEqual(material_value(self.sheet, self.material_category), 20)

    def test_spend_locks_the_bucket_row_before_mutating(self):
        """#2540 slice 3 review fold-in: spend_materials now locks the bucket row
        before checking/mutating it (mirrors currency.services.transfer's source
        lock) — concurrent same-bucket drains (two boon accepts against one NPC)
        became realistic once this task added the first caller that can trigger
        them. Not a threading test (deliberately, per the fold-in note) — this
        proves the mutate lands under a locked re-read rather than the prior
        unlocked filter().first(), by re-reading under select_for_update() inside
        the same transaction and asserting it sees the post-spend value."""
        credit_materials(self.sheet, self.material_category, 100)
        with transaction.atomic():
            spend_materials(self.sheet, self.material_category, 30)
            locked = MaterialBucket.objects.select_for_update().get(
                character_sheet=self.sheet, material_category=self.material_category
            )
            self.assertEqual(locked.value, 70)
        self.assertEqual(material_value(self.sheet, self.material_category), 70)

    def test_credit_locks_the_bucket_row_before_mutating(self):
        """Symmetric fold-in for credit_materials — see test_spend_locks_the_
        bucket_row_before_mutating."""
        credit_materials(self.sheet, self.material_category, 100)
        with transaction.atomic():
            credit_materials(self.sheet, self.material_category, 25)
            locked = MaterialBucket.objects.select_for_update().get(
                character_sheet=self.sheet, material_category=self.material_category
            )
            self.assertEqual(locked.value, 125)
        self.assertEqual(material_value(self.sheet, self.material_category), 125)


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
        self.material_category = MaterialCategoryFactory(name="Semiprecious Gems")
        self.recipe = CraftingRecipeFactory(
            requires_station=False, action_point_cost=0, anima_cost=0
        )
        CraftingMaterialRequirementFactory(
            recipe=self.recipe,
            item_template=None,
            material_category=self.material_category,
            required_value=100,
        )

    def test_affordable_when_bucket_covers_value(self):
        MaterialBucketFactory(
            character_sheet=self.sheet, material_category=self.material_category, value=150
        )
        staged = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        self.assertEqual(staged.bucket_spends, [(self.material_category, 100)])

    def test_unaffordable_when_bucket_short(self):
        MaterialBucketFactory(
            character_sheet=self.sheet, material_category=self.material_category, value=50
        )
        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_consume_spends_the_bucket(self):
        MaterialBucketFactory(
            character_sheet=self.sheet, material_category=self.material_category, value=150
        )
        staged = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        summary = consume_cost(
            crafter_character=self.character, staged=staged, consumption=CostConsumption.FULL
        )
        self.assertEqual(summary["material_value"], 100)
        self.assertEqual(material_value(self.sheet, self.material_category), 50)  # 150 - 100

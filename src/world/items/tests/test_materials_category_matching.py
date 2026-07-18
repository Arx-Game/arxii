"""Tests for material-category matching in gather_consumable_pks (Build 0a, Task 3)."""

from __future__ import annotations

from django.test import TestCase

from world.items.exceptions import InsufficientMaterials
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    CraftingRecipeFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    MaterialCategoryFactory,
    QualityTierFactory,
)
from world.items.services.materials import gather_consumable_pks


class CategoryMatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.recipe = CraftingRecipeFactory()
        cls.precious = MaterialCategoryFactory(name="Precious Gemstones")
        cls.ruby_tmpl = ItemTemplateFactory(name="Ruby", material_category=cls.precious)
        cls.sapphire_tmpl = ItemTemplateFactory(name="Sapphire", material_category=cls.precious)
        cls.iron_tmpl = ItemTemplateFactory(name="Iron Bar")  # no category

    def _category_req(self, quantity=1, min_quality_tier=None):
        return CraftingMaterialRequirementFactory(
            recipe=self.recipe,
            item_template=None,
            material_category=self.precious,
            quantity=quantity,
            min_quality_tier=min_quality_tier,
        )

    def test_category_requirement_pulls_across_member_templates(self):
        ruby = ItemInstanceFactory(template=self.ruby_tmpl, quantity=2)
        sapphire = ItemInstanceFactory(template=self.sapphire_tmpl, quantity=1)
        req = self._category_req(quantity=3)
        allocations = gather_consumable_pks(available=[ruby, sapphire], requirements=[req])
        self.assertEqual(sum(amt for _, amt in allocations), 3)

    def test_non_member_does_not_satisfy_category(self):
        iron = ItemInstanceFactory(template=self.iron_tmpl, quantity=5)
        req = self._category_req(quantity=1)
        with self.assertRaises(InsufficientMaterials):
            gather_consumable_pks(available=[iron], requirements=[req])

    def test_category_requirement_honors_min_quality_tier(self):
        low = QualityTierFactory(name="Rough", sort_order=1)
        high = QualityTierFactory(name="Flawless", sort_order=9)
        rough_ruby = ItemInstanceFactory(template=self.ruby_tmpl, quantity=1, quality_tier=low)
        req = self._category_req(quantity=1, min_quality_tier=high)
        with self.assertRaises(InsufficientMaterials):
            gather_consumable_pks(available=[rough_ruby], requirements=[req])

    def test_template_requirement_still_works(self):
        ruby = ItemInstanceFactory(template=self.ruby_tmpl, quantity=1)
        req = CraftingMaterialRequirementFactory(
            recipe=self.recipe, item_template=self.ruby_tmpl, quantity=1
        )
        allocations = gather_consumable_pks(available=[ruby], requirements=[req])
        self.assertEqual(allocations, [(ruby, 1)])

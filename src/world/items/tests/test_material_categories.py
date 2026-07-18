"""Tests for MaterialCategory and category-targeted crafting requirements (Build 0a)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.items.factories import (
    CraftingMaterialRequirementFactory,
    CraftingRecipeFactory,
    ItemTemplateFactory,
    MaterialCategoryFactory,
)


class MaterialCategoryModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.precious = MaterialCategoryFactory(name="Precious Gemstones")

    def test_category_str_is_name(self):
        self.assertEqual(str(self.precious), "Precious Gemstones")

    def test_template_belongs_to_category(self):
        ruby = ItemTemplateFactory(name="Ruby", material_category=self.precious)
        self.assertEqual(ruby.material_category, self.precious)
        self.assertIn(ruby, self.precious.templates.all())

    def test_template_category_defaults_null(self):
        plain = ItemTemplateFactory(name="Iron Bar")
        self.assertIsNone(plain.material_category_id)


class CraftingMaterialRequirementCategoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.recipe = CraftingRecipeFactory()
        cls.precious = MaterialCategoryFactory(name="Precious Gemstones")

    def test_category_requirement_has_null_template(self):
        req = CraftingMaterialRequirementFactory(
            recipe=self.recipe,
            item_template=None,
            material_category=self.precious,
            quantity=3,
        )
        self.assertIsNone(req.item_template_id)
        self.assertEqual(req.material_category_id, self.precious.pk)

    def test_both_set_violates_constraint(self):
        ruby = ItemTemplateFactory(name="Ruby", material_category=self.precious)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CraftingMaterialRequirementFactory(
                recipe=self.recipe,
                item_template=ruby,
                material_category=self.precious,
            )

    def test_neither_set_violates_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CraftingMaterialRequirementFactory(
                recipe=self.recipe,
                item_template=None,
                material_category=None,
            )

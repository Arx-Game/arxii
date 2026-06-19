"""Tests for world.items.crafting models — Task 1: CraftingRecipe."""

from django.test import TestCase

from world.items.crafting.constants import PARTIAL_FRACTION, CostConsumption, CraftingRecipeKind
from world.items.crafting.models import CraftingRecipe
from world.items.factories import CraftingRecipeFactory


class CraftingRecipeModelTests(TestCase):
    """Tests for the CraftingRecipe model."""

    def test_create_and_str(self) -> None:
        """Factory creates a valid CraftingRecipe; str returns name; defaults are correct."""
        recipe = CraftingRecipeFactory(name="Attach Facet", kind=CraftingRecipeKind.FACET_ATTACH)
        self.assertEqual(str(recipe), "Attach Facet")
        self.assertEqual(recipe.kind, CraftingRecipeKind.FACET_ATTACH)
        self.assertEqual(recipe.default_cost_consumption, CostConsumption.FULL)
        self.assertEqual(recipe.base_difficulty, 0)
        self.assertEqual(recipe.success_level_step, 10)
        self.assertEqual(recipe.min_success_level, 1)
        self.assertEqual(recipe.action_point_cost, 0)
        self.assertEqual(recipe.anima_cost, 0)
        self.assertIsNone(recipe.check_type)
        self.assertIsNone(recipe.skill_trait)

    def test_kind_choices(self) -> None:
        """CraftingRecipeKind has FACET_ATTACH and STYLE_ATTACH choices."""
        self.assertIn(CraftingRecipeKind.FACET_ATTACH, CraftingRecipeKind.values)
        self.assertIn(CraftingRecipeKind.STYLE_ATTACH, CraftingRecipeKind.values)

    def test_cost_consumption_choices(self) -> None:
        """CostConsumption has NONE, PARTIAL, FULL choices."""
        self.assertIn(CostConsumption.NONE, CostConsumption.values)
        self.assertIn(CostConsumption.PARTIAL, CostConsumption.values)
        self.assertIn(CostConsumption.FULL, CostConsumption.values)

    def test_partial_fraction_value(self) -> None:
        """PARTIAL_FRACTION is 0.5."""
        self.assertEqual(PARTIAL_FRACTION, 0.5)

    def test_unique_kind_constraint(self) -> None:
        """Two recipes with the same kind violate the unique constraint."""
        from django.db import IntegrityError

        CraftingRecipeFactory(name="Attach Facet", kind=CraftingRecipeKind.FACET_ATTACH)
        with self.assertRaises(IntegrityError):
            CraftingRecipeFactory(name="Attach Facet 2", kind=CraftingRecipeKind.FACET_ATTACH)

    def test_ordering(self) -> None:
        """CraftingRecipe default ordering is by name."""
        CraftingRecipeFactory(name="Zebra Recipe", kind=CraftingRecipeKind.STYLE_ATTACH)
        CraftingRecipeFactory(name="Alpha Recipe", kind=CraftingRecipeKind.FACET_ATTACH)
        names = list(CraftingRecipe.objects.values_list("name", flat=True))
        self.assertEqual(names, sorted(names))

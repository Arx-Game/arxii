"""Tests for world.items.crafting models — Task 1 & 2: CraftingRecipe and related models."""

from django.db import IntegrityError
from django.test import TestCase

from world.items.crafting.constants import PARTIAL_FRACTION, CostConsumption, CraftingRecipeKind
from world.items.crafting.models import CraftingRecipe, CraftingSkillCap
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    CraftingRecipeConsequenceFactory,
    CraftingRecipeFactory,
    CraftingSkillCapFactory,
    QualityTierFactory,
)


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

    def test_two_bare_factory_calls_reuse_the_same_kind_row(self) -> None:
        """Two bare ``CraftingRecipeFactory()`` calls return the same row, not IntegrityError.

        ``kind`` is unique; the factory keys ``django_get_or_create`` on it so the second
        bare call reuses the FACET_ATTACH recipe instead of violating the constraint (#1243).
        """
        first = CraftingRecipeFactory()
        second = CraftingRecipeFactory()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            CraftingRecipe.objects.filter(kind=CraftingRecipeKind.FACET_ATTACH).count(), 1
        )

    def test_distinct_kinds_create_distinct_rows(self) -> None:
        """Passing a distinct ``kind`` still creates a separate recipe."""
        facet = CraftingRecipeFactory(kind=CraftingRecipeKind.FACET_ATTACH)
        style = CraftingRecipeFactory(kind=CraftingRecipeKind.STYLE_ATTACH)
        self.assertNotEqual(facet.pk, style.pk)

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
        CraftingRecipeFactory(name="Attach Facet", kind=CraftingRecipeKind.FACET_ATTACH)
        # The factory get_or_creates on ``kind`` (so a second factory call would reuse the
        # row); assert the DB constraint directly via the model to exercise it (#1243).
        with self.assertRaises(IntegrityError):
            CraftingRecipe.objects.create(
                name="Attach Facet 2", kind=CraftingRecipeKind.FACET_ATTACH
            )

    def test_ordering(self) -> None:
        """CraftingRecipe default ordering is by name."""
        CraftingRecipeFactory(name="Zebra Recipe", kind=CraftingRecipeKind.STYLE_ATTACH)
        CraftingRecipeFactory(name="Alpha Recipe", kind=CraftingRecipeKind.FACET_ATTACH)
        names = list(CraftingRecipe.objects.values_list("name", flat=True))
        self.assertEqual(names, sorted(names))


class CraftingMaterialRequirementTests(TestCase):
    """Tests for the CraftingMaterialRequirement model (Task 2)."""

    def test_material_requirement_fields(self) -> None:
        """Factory produces a valid CraftingMaterialRequirement with correct field values."""
        recipe = CraftingRecipeFactory(name="Shared Recipe", kind=CraftingRecipeKind.FACET_ATTACH)
        req = CraftingMaterialRequirementFactory(recipe=recipe)
        self.assertIsNotNone(req.recipe)
        self.assertIsNotNone(req.item_template)
        self.assertGreater(req.quantity, 0)
        # min_quality_tier is optional — check it can be null
        req_no_tier = CraftingMaterialRequirementFactory(recipe=recipe, min_quality_tier=None)
        self.assertIsNone(req_no_tier.min_quality_tier)

    def test_material_requirement_related_name(self) -> None:
        """material_requirements reverse manager exists on CraftingRecipe."""
        req = CraftingMaterialRequirementFactory()
        self.assertIn(req, req.recipe.material_requirements.all())

    def test_material_requirement_str(self) -> None:
        """str() returns a meaningful representation."""
        req = CraftingMaterialRequirementFactory()
        self.assertIsInstance(str(req), str)


class CraftingSkillCapTests(TestCase):
    """Tests for CraftingSkillCap.for_skill classmethod (Task 2)."""

    def setUp(self) -> None:
        self.recipe = CraftingRecipeFactory(
            name="Skill Cap Recipe", kind=CraftingRecipeKind.FACET_ATTACH
        )
        self.common = QualityTierFactory(name="Common", sort_order=0, numeric_min=0, numeric_max=49)
        self.fine = QualityTierFactory(name="Fine", sort_order=1, numeric_min=50, numeric_max=79)
        self.masterwork = QualityTierFactory(
            name="Masterwork", sort_order=2, numeric_min=80, numeric_max=100
        )
        CraftingSkillCapFactory(recipe=self.recipe, min_skill_value=0, max_quality_tier=self.common)
        CraftingSkillCapFactory(recipe=self.recipe, min_skill_value=50, max_quality_tier=self.fine)
        CraftingSkillCapFactory(
            recipe=self.recipe, min_skill_value=80, max_quality_tier=self.masterwork
        )

    def test_for_skill_returns_highest_band(self) -> None:
        """for_skill returns the max_quality_tier for the highest qualifying band."""
        result = CraftingSkillCap.for_skill(self.recipe, 60)
        self.assertEqual(result.name, "Fine")  # type: ignore[union-attr]

    def test_for_skill_returns_common_at_low_value(self) -> None:
        """for_skill at skill_value=10 returns Common (min_skill_value=0)."""
        result = CraftingSkillCap.for_skill(self.recipe, 10)
        self.assertEqual(result.name, "Common")  # type: ignore[union-attr]

    def test_for_skill_returns_masterwork_at_high_value(self) -> None:
        """for_skill at skill_value=90 returns Masterwork."""
        result = CraftingSkillCap.for_skill(self.recipe, 90)
        self.assertEqual(result.name, "Masterwork")  # type: ignore[union-attr]

    def test_for_skill_no_rows_returns_none(self) -> None:
        """for_skill returns None when no skill cap rows exist for the recipe."""
        empty_recipe = CraftingRecipeFactory(
            name="Empty Recipe", kind=CraftingRecipeKind.STYLE_ATTACH
        )
        result = CraftingSkillCap.for_skill(empty_recipe, 60)
        self.assertIsNone(result)

    def test_skill_cap_unique_constraint(self) -> None:
        """Duplicate (recipe, min_skill_value) pair raises IntegrityError."""
        with self.assertRaises(IntegrityError):
            CraftingSkillCapFactory(
                recipe=self.recipe, min_skill_value=0, max_quality_tier=self.fine
            )

    def test_for_skill_at_exact_boundary(self) -> None:
        """for_skill at exactly min_skill_value=50 returns Fine (<=, not <)."""
        result = CraftingSkillCap.for_skill(self.recipe, 50)
        self.assertEqual(result.name, "Fine")  # type: ignore[union-attr]

    def test_skill_cap_related_name(self) -> None:
        """skill_caps reverse manager exists on CraftingRecipe."""
        caps = list(self.recipe.skill_caps.all())
        self.assertEqual(len(caps), 3)


class CraftingRecipeConsequenceTests(TestCase):
    """Tests for the CraftingRecipeConsequence model (Task 2)."""

    def test_recipe_consequence_unique(self) -> None:
        """Duplicate (recipe, consequence) pair raises IntegrityError."""
        row = CraftingRecipeConsequenceFactory()
        with self.assertRaises(IntegrityError):
            CraftingRecipeConsequenceFactory(recipe=row.recipe, consequence=row.consequence)

    def test_consequence_fields(self) -> None:
        """Factory produces a valid CraftingRecipeConsequence with expected fields."""
        recipe = CraftingRecipeFactory(
            name="Consequence Recipe", kind=CraftingRecipeKind.FACET_ATTACH
        )
        row = CraftingRecipeConsequenceFactory(recipe=recipe)
        self.assertIsNotNone(row.recipe)
        self.assertIsNotNone(row.consequence)
        self.assertIn(row.cost_consumption, CostConsumption.values)
        # weight_override is optional — create a new consequence to avoid unique constraint
        row_no_override = CraftingRecipeConsequenceFactory(recipe=recipe, weight_override=None)
        self.assertIsNone(row_no_override.weight_override)

    def test_consequence_related_name(self) -> None:
        """consequence_rows reverse manager exists on CraftingRecipe."""
        row = CraftingRecipeConsequenceFactory()
        self.assertIn(row, row.recipe.consequence_rows.all())

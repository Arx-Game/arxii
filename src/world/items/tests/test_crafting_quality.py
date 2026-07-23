"""Tests for world.items.crafting.quality — skill-gated quality cap clamp.

TDD test suite per task-5-brief.md. Covers:
  - High check score + low-skill crafter whose cap is a low tier → clamped to the cap tier.
  - No CraftingSkillCap rows → uncapped (raw score's tier is returned).
  - Cap tier is above the raw score's tier → no effect (score's natural tier returned).
  - No QualityTier rows → CraftingNotConfigured raised.
"""

from types import SimpleNamespace

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.quality import resolve_capped_tier
from world.items.exceptions import CraftingNotConfigured
from world.items.factories import (
    CraftingRecipeFactory,
    CraftingSkillCapFactory,
    QualityTierFactory,
)
from world.traits.factories import CharacterTraitValueFactory, TraitFactory
from world.traits.models import TraitCategory, TraitType


def _check_result(*, total_points: int, success_level: int) -> SimpleNamespace:
    """Build a minimal duck-typed CheckResult for compute_quality_score."""
    return SimpleNamespace(total_points=total_points, success_level=success_level)


class _QualityResolutionBase(TestCase):
    """Shared setUp: tiers, recipe with skill_trait, and a crafter character."""

    def setUp(self) -> None:
        # Seed three quality tiers with non-overlapping numeric ranges.
        self.common = QualityTierFactory(name="Common", numeric_min=0, numeric_max=49, sort_order=0)
        self.fine = QualityTierFactory(name="Fine", numeric_min=50, numeric_max=79, sort_order=1)
        self.masterwork = QualityTierFactory(
            name="Masterwork", numeric_min=80, numeric_max=200, sort_order=2
        )

        # A skill trait for the recipe.
        self.skill = TraitFactory(
            name="Enchanting",
            trait_type=TraitType.SKILL,
            category=TraitCategory.CRAFTING,
        )

        # A recipe referencing that trait; success_level_step=10, min_success_level=1.
        self.recipe = CraftingRecipeFactory(
            success_level_step=10,
            min_success_level=1,
            skill_trait=self.skill,
        )

        # A character with a CharacterSheet so .traits handler works.
        self.character = CharacterFactory()
        CharacterSheetFactory(character=self.character)


class CapClampTests(_QualityResolutionBase):
    """A crafter whose skill cap is below the raw check score is clamped to the cap tier."""

    def test_high_score_low_skill_clamped_to_cap_tier(self) -> None:
        """A crit-level score (Masterwork range) is clamped to Common when skill is low."""
        # Low-skill crafter: skill=5.  Cap band: min_skill_value=0 → Common (0–49).
        CharacterTraitValueFactory(character=self.character.sheet_data, trait=self.skill, value=5)
        CraftingSkillCapFactory(recipe=self.recipe, min_skill_value=0, max_quality_tier=self.common)

        # check_result with total_points=90, success_level=1 → score=90+0=90 → Masterwork
        # but cap.numeric_max = 49 → score clamped to 49 → Common.
        result = resolve_capped_tier(
            recipe=self.recipe,
            crafter_character=self.character,
            check_result=_check_result(total_points=90, success_level=1),
        )

        self.assertEqual(result, self.common)

    def test_cap_is_enforced_not_raw_tier(self) -> None:
        """Confirm the capped tier differs from the tier the unclamped score would give."""
        CharacterTraitValueFactory(character=self.character.sheet_data, trait=self.skill, value=5)
        CraftingSkillCapFactory(recipe=self.recipe, min_skill_value=0, max_quality_tier=self.common)

        # Raw score = 100 + (3-1)*10 = 120 → Masterwork; cap clamps to 49 → Common.
        result = resolve_capped_tier(
            recipe=self.recipe,
            crafter_character=self.character,
            check_result=_check_result(total_points=100, success_level=3),
        )

        self.assertNotEqual(result, self.masterwork)
        self.assertEqual(result, self.common)


class NoCapsTests(_QualityResolutionBase):
    """When no CraftingSkillCap rows exist the raw score tier is returned unclamped."""

    def test_no_cap_rows_returns_raw_score_tier(self) -> None:
        """Without skill caps a high-scoring crafter gets Masterwork."""
        CharacterTraitValueFactory(character=self.character.sheet_data, trait=self.skill, value=5)
        # No CraftingSkillCap rows created.

        result = resolve_capped_tier(
            recipe=self.recipe,
            crafter_character=self.character,
            check_result=_check_result(total_points=90, success_level=1),
        )

        self.assertEqual(result, self.masterwork)


class CapAboveScoreTests(_QualityResolutionBase):
    """A cap tier that is above the raw score's tier has no effect."""

    def test_cap_above_score_returns_natural_tier(self) -> None:
        """Cap at Masterwork (200) does not artificially inflate a Common-range score."""
        CharacterTraitValueFactory(character=self.character.sheet_data, trait=self.skill, value=80)
        CraftingSkillCapFactory(
            recipe=self.recipe, min_skill_value=0, max_quality_tier=self.masterwork
        )

        # Raw score = 20 + 0 = 20 → Common; cap.numeric_max = 200 → min(20, 200) = 20 → Common.
        result = resolve_capped_tier(
            recipe=self.recipe,
            crafter_character=self.character,
            check_result=_check_result(total_points=20, success_level=1),
        )

        self.assertEqual(result, self.common)


class NoSkillTraitTests(TestCase):
    """When recipe.skill_trait is None, the skill cap is skipped entirely."""

    def setUp(self) -> None:
        self.common = QualityTierFactory(name="Common", numeric_min=0, numeric_max=49, sort_order=0)
        self.fine = QualityTierFactory(name="Fine", numeric_min=50, numeric_max=79, sort_order=1)
        self.masterwork = QualityTierFactory(
            name="Masterwork", numeric_min=80, numeric_max=200, sort_order=2
        )

        # Recipe with no skill trait.
        self.recipe = CraftingRecipeFactory(
            success_level_step=10,
            min_success_level=1,
            skill_trait=None,
        )
        # Cap rows exist but should be ignored.
        CraftingSkillCapFactory(recipe=self.recipe, min_skill_value=0, max_quality_tier=self.common)

        self.character = CharacterFactory()
        CharacterSheetFactory(character=self.character)

    def test_no_skill_trait_returns_uncapped_tier(self) -> None:
        """A recipe with skill_trait=None returns the raw score's tier without raising."""
        result = resolve_capped_tier(
            recipe=self.recipe,
            crafter_character=self.character,
            check_result=_check_result(total_points=90, success_level=1),
        )

        # score = 90 + (1-1)*10 = 90 → Masterwork (uncapped).
        self.assertEqual(result, self.masterwork)


class NoTiersSeededTests(TestCase):
    """When no QualityTier rows are seeded, CraftingNotConfigured is raised."""

    def setUp(self) -> None:
        self.skill = TraitFactory(
            name="EnchantingUncfg",
            trait_type=TraitType.SKILL,
            category=TraitCategory.CRAFTING,
        )
        self.recipe = CraftingRecipeFactory(
            success_level_step=10,
            min_success_level=1,
            skill_trait=self.skill,
        )
        self.character = CharacterFactory()
        CharacterSheetFactory(character=self.character)
        CharacterTraitValueFactory(character=self.character.sheet_data, trait=self.skill, value=10)

    def test_raises_crafting_not_configured_when_no_tiers(self) -> None:
        """resolve_capped_tier raises CraftingNotConfigured if QualityTier table is empty."""
        with self.assertRaises(CraftingNotConfigured):
            resolve_capped_tier(
                recipe=self.recipe,
                crafter_character=self.character,
                check_result=_check_result(total_points=50, success_level=1),
            )

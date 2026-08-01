"""Tests for #2878 Phase A: material grade term + thread-capped quality rungs.

Covers:
  - ``_material_grade_bonus``: quantity-weighted mean of staged materials' grades.
  - ``material_grade_bonus`` lifting the resolved tier through ``resolve_capped_tier``.
  - Thread ceiling: 0 threads clamps at rung BASE_MAX_QUALITY_RUNG; each active
    TRAIT thread on the recipe's skill raises the reachable rung by one; retired
    threads and other-trait threads don't count.
  - Backward compatibility: ladders with no rows above the allowed rung are
    never clamped (the existing 3-row test ladders).
"""

from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.cost import StagedCost
from world.items.crafting.quality import resolve_capped_tier, thread_count_for_skill
from world.items.crafting.services import _material_grade_bonus
from world.items.factories import (
    CraftingRecipeFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.magic.factories import ThreadFactory
from world.traits.factories import TraitFactory
from world.traits.models import TraitCategory, TraitType


def _check_result(*, total_points: int, success_level: int) -> SimpleNamespace:
    return SimpleNamespace(total_points=total_points, success_level=success_level)


class MaterialGradeBonusTests(TestCase):
    """_material_grade_bonus is the quantity-weighted mean template grade."""

    def test_weighted_mean_rounds(self) -> None:
        steel = ItemInstanceFactory(template=ItemTemplateFactory(material_grade=10))
        alaricite = ItemInstanceFactory(template=ItemTemplateFactory(material_grade=40))
        staged = StagedCost(
            action_points=0,
            anima=0,
            material_allocations=[(steel, 3), (alaricite, 1)],
        )
        # (10*3 + 40*1) / 4 = 17.5 → round-half-even = 18
        self.assertEqual(_material_grade_bonus(staged), 18)

    def test_no_materials_is_zero(self) -> None:
        staged = StagedCost(action_points=2, anima=0)
        self.assertEqual(_material_grade_bonus(staged), 0)


class GradeLiftsTierTests(TestCase):
    """The grade term shifts the quality score before tier resolution."""

    def setUp(self) -> None:
        self.low = QualityTierFactory(name="Low", numeric_min=0, numeric_max=49, sort_order=1)
        self.high = QualityTierFactory(name="High", numeric_min=50, numeric_max=200, sort_order=2)
        self.recipe = CraftingRecipeFactory(
            success_level_step=10, min_success_level=1, skill_trait=None
        )
        self.character = CharacterSheetFactory().character

    def test_grade_bonus_crosses_tier_boundary(self) -> None:
        result = _check_result(total_points=40, success_level=1)
        without = resolve_capped_tier(
            recipe=self.recipe, crafter_character=self.character, check_result=result
        )
        with_grade = resolve_capped_tier(
            recipe=self.recipe,
            crafter_character=self.character,
            check_result=result,
            material_grade_bonus=15,
        )
        self.assertEqual(without, self.low)
        self.assertEqual(with_grade, self.high)


class ThreadCeilingTests(TestCase):
    """Rungs above BASE_MAX_QUALITY_RUNG (9) + thread count are unreachable."""

    def setUp(self) -> None:
        self.perfect = QualityTierFactory(
            name="Perfect", numeric_min=0, numeric_max=99, sort_order=9
        )
        self.divine = QualityTierFactory(
            name="Divine", numeric_min=100, numeric_max=119, sort_order=10
        )
        self.transcendent = QualityTierFactory(
            name="Transcendent", numeric_min=120, numeric_max=9999, sort_order=11
        )
        self.skill = TraitFactory(
            name="Smithing", trait_type=TraitType.SKILL, category=TraitCategory.CRAFTING
        )
        # No CraftingSkillCap rows: isolate the thread ceiling.
        self.recipe = CraftingRecipeFactory(
            success_level_step=10, min_success_level=1, skill_trait=self.skill
        )
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.divine_score = _check_result(total_points=100, success_level=1)

    def test_mundane_crafter_capped_below_divine(self) -> None:
        tier = resolve_capped_tier(
            recipe=self.recipe, crafter_character=self.character, check_result=self.divine_score
        )
        self.assertEqual(tier, self.perfect)

    def test_one_thread_reaches_divine_but_not_transcendent(self) -> None:
        ThreadFactory(owner=self.sheet, target_trait=self.skill)
        self.assertEqual(thread_count_for_skill(self.character, self.skill), 1)
        tier = resolve_capped_tier(
            recipe=self.recipe, crafter_character=self.character, check_result=self.divine_score
        )
        self.assertEqual(tier, self.divine)
        transcendent_score = _check_result(total_points=150, success_level=1)
        tier = resolve_capped_tier(
            recipe=self.recipe,
            crafter_character=self.character,
            check_result=transcendent_score,
        )
        self.assertEqual(tier, self.divine)

    def test_retired_and_other_trait_threads_do_not_count(self) -> None:
        ThreadFactory(owner=self.sheet, target_trait=self.skill, retired_at=timezone.now())
        other = TraitFactory(
            name="Sewing", trait_type=TraitType.SKILL, category=TraitCategory.CRAFTING
        )
        ThreadFactory(owner=self.sheet, target_trait=other)
        self.assertEqual(thread_count_for_skill(self.character, self.skill), 0)
        tier = resolve_capped_tier(
            recipe=self.recipe, crafter_character=self.character, check_result=self.divine_score
        )
        self.assertEqual(tier, self.perfect)


class ShortLadderCompatibilityTests(TestCase):
    """Ladders with no rows above the allowed rung are never thread-clamped."""

    def test_three_row_ladder_unclamped(self) -> None:
        top = QualityTierFactory(name="Top", numeric_min=0, numeric_max=9999, sort_order=2)
        recipe = CraftingRecipeFactory(success_level_step=10, min_success_level=1, skill_trait=None)
        character = CharacterSheetFactory().character
        tier = resolve_capped_tier(
            recipe=recipe,
            crafter_character=character,
            check_result=_check_result(total_points=5000, success_level=1),
        )
        self.assertEqual(tier, top)

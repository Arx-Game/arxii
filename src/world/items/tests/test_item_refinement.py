"""Tests for #2878 Phase C: refinement projects — the guaranteed long road.

Covers:
  - start_item_refinement: threshold scales with value × rung; duplicate and
    impossible goals rejected.
  - Deterministic completion: funding the threshold applies +1 (new Accent at
    level 1; existing Accent raised; base quality rung raised, crafted-recipe
    snapshot kept in step) with NO rolls anywhere.
  - The master gate: the crossing contribution raises RefinementAwaitsMaster
    when nobody on the project can reach the goal rung.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.items.crafting.models import ItemAccent
from world.items.crafting.refinement import (
    donate_to_item_refinement,
    refinement_threshold,
    start_item_refinement,
)
from world.items.exceptions import RefinementAwaitsMaster, RefinementNotPossible
from world.items.factories import (
    CraftingRecipeFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.items.models import AccentLevel
from world.magic.factories import ThreadFactory
from world.mechanics.factories import ModifierTargetFactory
from world.projects.constants import ProjectStatus
from world.traits.factories import TraitFactory
from world.traits.models import TraitCategory, TraitType


def _accent_ladder() -> None:
    for level, name in (
        (1, "slightly"),
        (2, "modestly"),
        (3, "quite"),
        (4, "very"),
        (5, "extremely"),
    ):
        AccentLevel.objects.get_or_create(level=level, defaults={"name": name})


class RefinementProjectTests(TestCase):
    def setUp(self) -> None:
        _accent_ladder()
        self.tier3 = QualityTierFactory(name="Average", numeric_min=0, numeric_max=29, sort_order=3)
        self.tier4 = QualityTierFactory(
            name="Above Average", numeric_min=30, numeric_max=39, sort_order=4
        )
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.item = ItemInstanceFactory(
            template=ItemTemplateFactory(value=1000),
            holder_character_sheet=self.sheet,
            quality_tier=self.tier3,
        )
        self.menace = ModifierTargetFactory(name="menace", is_styleable=True)

    def _fund(self, project, coppers: int) -> None:
        purse = get_or_create_purse(self.sheet)
        transfer(amount=coppers, reason="test-faucet", to_purse=purse)
        donate_to_item_refinement(project, donor_persona=self.persona, amount=coppers)

    def test_threshold_scales_with_value_and_rung(self) -> None:
        # New accent: rung 1 → 1000 × 1 / 100 = 10 progress.
        self.assertEqual(refinement_threshold(self.item, 1), 10)
        # Quality: rung 4 → 1000 × 4 / 100 = 40 progress.
        self.assertEqual(refinement_threshold(self.item, 4), 40)

    def test_fund_new_accent_completes_deterministically(self) -> None:
        project = start_item_refinement(
            item_instance=self.item, initiator_persona=self.persona, accent_target=self.menace
        )
        self._fund(project, 1000)  # 10 progress = threshold
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        accent = ItemAccent.objects.get(item_instance=self.item, target=self.menace)
        self.assertEqual(accent.level.level, 1)

    def test_fund_quality_rung_updates_item_and_snapshot(self) -> None:
        from world.items.crafting.models import CraftedItemRecipe

        recipe = CraftingRecipeFactory()
        CraftedItemRecipe.objects.create(
            item_instance=self.item, recipe=recipe, quality_tier=self.tier3
        )
        project = start_item_refinement(
            item_instance=self.item, initiator_persona=self.persona, accent_target=None
        )
        self._fund(project, 4000)  # rung 4 → 40 progress
        project.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(self.item.quality_tier, self.tier4)
        crafted = CraftedItemRecipe.objects.get(item_instance=self.item)
        self.assertEqual(crafted.quality_tier, self.tier4)

    def test_duplicate_goal_rejected(self) -> None:
        start_item_refinement(
            item_instance=self.item, initiator_persona=self.persona, accent_target=self.menace
        )
        with self.assertRaises(RefinementNotPossible):
            start_item_refinement(
                item_instance=self.item,
                initiator_persona=self.persona,
                accent_target=self.menace,
            )

    def test_no_higher_quality_rung_rejected(self) -> None:
        item = ItemInstanceFactory(
            template=ItemTemplateFactory(value=100),
            holder_character_sheet=self.sheet,
            quality_tier=self.tier4,  # top of the seeded ladder in this test
        )
        with self.assertRaises(RefinementNotPossible):
            start_item_refinement(item_instance=item, initiator_persona=self.persona)


class MasterGateTests(TestCase):
    """The crossing contribution needs a contributor whose cap reaches the goal."""

    def setUp(self) -> None:
        _accent_ladder()
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.skill = TraitFactory(
            name="Smithing", trait_type=TraitType.SKILL, category=TraitCategory.CRAFTING
        )
        self.menace = ModifierTargetFactory(name="menace", is_styleable=True)
        self.item = ItemInstanceFactory(
            template=ItemTemplateFactory(value=1000), holder_character_sheet=self.sheet
        )
        from world.items.crafting.models import CraftedItemRecipe

        recipe = CraftingRecipeFactory(skill_trait=self.skill)
        tier = QualityTierFactory(name="Average", numeric_min=0, numeric_max=29, sort_order=3)
        CraftedItemRecipe.objects.create(item_instance=self.item, recipe=recipe, quality_tier=tier)
        # Push the existing accent to the mundane ceiling (4); goal becomes 5.
        ItemAccent.objects.create(
            item_instance=self.item,
            target=self.menace,
            level=AccentLevel.objects.get(level=4),
        )

    def _fund(self, project, coppers: int) -> None:
        purse = get_or_create_purse(self.sheet)
        transfer(amount=coppers, reason="test-faucet", to_purse=purse)
        donate_to_item_refinement(project, donor_persona=self.persona, amount=coppers)

    def test_crossing_contribution_blocked_without_master(self) -> None:
        project = start_item_refinement(
            item_instance=self.item, initiator_persona=self.persona, accent_target=self.menace
        )
        # Goal rung 5 > mundane cap 4 and no threads anywhere on the project.
        # (Threshold is 1000×5÷100 = 50, doubled to 100 by the existing accent
        # — #2886 — so 10000 coppers is the crossing contribution.)
        with self.assertRaises(RefinementAwaitsMaster):
            self._fund(project, 10000)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.ACTIVE)
        self.assertEqual(project.current_progress, 0)

    def test_thread_woven_contributor_crosses(self) -> None:
        ThreadFactory(owner=self.sheet, target_trait=self.skill)  # cap 4+1=5
        project = start_item_refinement(
            item_instance=self.item, initiator_persona=self.persona, accent_target=self.menace
        )
        self._fund(project, 10000)  # 50-progress threshold doubled by the accent (#2886)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        accent = ItemAccent.objects.get(item_instance=self.item, target=self.menace)
        self.assertEqual(accent.level.level, 5)

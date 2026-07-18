"""End-to-end: crafting availability query honors category requirements (Build 0a, Task 4)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.items.crafting.constants import CraftingRecipeKind
from world.items.crafting.cost import stage_and_assert_affordable
from world.items.crafting.services import build_crafting_quote
from world.items.exceptions import CategoryRequirementsNotQuotable, CraftingCostUnaffordable
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    CraftingRecipeFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    MaterialCategoryFactory,
)


class CraftingCategoryRequirementTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.precious = MaterialCategoryFactory(name="Precious Gemstones")
        self.ruby_tmpl = ItemTemplateFactory(name="Ruby", material_category=self.precious)
        self.recipe = CraftingRecipeFactory(
            requires_station=False,
            action_point_cost=0,
            anima_cost=0,
            check_type=CheckTypeFactory(),
        )
        CraftingMaterialRequirementFactory(
            recipe=self.recipe,
            item_template=None,
            material_category=self.precious,
            quantity=2,
        )

    def test_holding_category_member_is_affordable(self) -> None:
        ItemInstanceFactory(template=self.ruby_tmpl, quantity=2, holder_character_sheet=self.sheet)
        staged = stage_and_assert_affordable(
            recipe=self.recipe,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
        )
        self.assertEqual(sum(amt for _, amt in staged.material_allocations), 2)

    def test_holding_nothing_is_unaffordable(self) -> None:
        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_non_member_holding_is_unaffordable(self) -> None:
        other_tmpl = ItemTemplateFactory(name="Copper Ingot")  # no category
        ItemInstanceFactory(template=other_tmpl, quantity=5, holder_character_sheet=self.sheet)
        with self.assertRaises(CraftingCostUnaffordable):
            stage_and_assert_affordable(
                recipe=self.recipe,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

    def test_quote_guards_category_requirements(self) -> None:
        # The read-only quote preview cannot represent a material class yet; it
        # raises a clear typed error rather than crashing (execution still works).
        with self.assertRaises(CategoryRequirementsNotQuotable):
            build_crafting_quote(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
            )

"""Tests for gem cutting (Build 0b slice 3)."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.action_points.factories import ActionPointPoolFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.crafting.constants import CraftingRecipeKind
from world.items.exceptions import CraftingCostUnaffordable, NotAGem
from world.items.factories import (
    CraftingRecipeFactory,
    GemGradeFactory,
    GemInstanceDetailsFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.items.gems.constants import GemAxis
from world.items.gems.services import cut_gem, resolve_cut_grade
from world.items.models import ItemInstance
from world.traits.factories import CheckOutcomeFactory


class CutLadderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uncut = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=1, label="uncut", multiplier=Decimal("1.0")
        )
        cls.rough = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=2, label="rough", multiplier=Decimal("1.2")
        )
        cls.fine = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=3, label="fine", multiplier=Decimal("1.5")
        )
        cls.brilliant = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=4, label="brilliant", multiplier=Decimal("2.0")
        )

    def test_resolve_advances_by_success_level(self):
        self.assertEqual(resolve_cut_grade(self.uncut, 1), self.rough)
        self.assertEqual(resolve_cut_grade(self.uncut, 2), self.fine)

    def test_resolve_caps_at_top(self):
        self.assertEqual(resolve_cut_grade(self.fine, 9), self.brilliant)

    def test_resolve_never_below_current(self):
        # A minimal success (level 1) still advances at least one step, never down.
        self.assertEqual(resolve_cut_grade(self.brilliant, 1), self.brilliant)


class CutGemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uncut = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=1, label="uncut", multiplier=Decimal("1.0")
        )
        cls.rough = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=2, label="rough", multiplier=Decimal("1.2")
        )
        cls.fine = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=3, label="fine", multiplier=Decimal("1.5")
        )
        cls.brilliant = GemGradeFactory(
            axis=GemAxis.CUT, sort_order=4, label="brilliant", multiplier=Decimal("2.0")
        )

    def setUp(self):
        self.character = CharacterFactory()
        self.pool = ActionPointPoolFactory(character=self.character, current=200, maximum=200)
        self.recipe = CraftingRecipeFactory(
            kind=CraftingRecipeKind.GEM_CUT,
            check_type=CheckTypeFactory(),
            min_success_level=1,
            action_point_cost=5,
        )

    def _gem(self, value=100, cut=None):
        tmpl = ItemTemplateFactory(value=value)
        inst = ItemInstanceFactory(template=tmpl)
        GemInstanceDetailsFactory(
            item_instance=inst,
            size_grade=GemGradeFactory(axis=GemAxis.SIZE, multiplier=Decimal("1.0")),
            purity_grade=GemGradeFactory(axis=GemAxis.PURITY, multiplier=Decimal("1.0")),
            cut_grade=cut or self.uncut,
        )
        inst.refresh_from_db()
        return inst

    def test_success_improves_cut_and_worth(self):
        gem = self._gem(value=100)  # uncut → worth 100
        with force_check_outcome(CheckOutcomeFactory(name="CutOk", success_level=2)):
            result = cut_gem(gem_instance=gem, crafter_character=self.character, recipe=self.recipe)
        self.assertFalse(result.shattered)
        # uncut + 2 → fine (×1.5) → worth 150
        self.assertEqual(result.new_cut_grade, self.fine)
        self.assertEqual(result.worth, 150)

    def test_botch_shatters_the_stone(self):
        gem = self._gem(value=100)
        gem_pk = gem.pk
        with force_check_outcome(CheckOutcomeFactory(name="CutBotch", success_level=-1)):
            result = cut_gem(gem_instance=gem, crafter_character=self.character, recipe=self.recipe)
        self.assertTrue(result.shattered)
        self.assertEqual(result.worth_lost, 100)
        self.assertFalse(ItemInstance.objects.filter(pk=gem_pk).exists())

    def test_ap_spent_on_the_attempt(self):
        gem = self._gem()
        with force_check_outcome(CheckOutcomeFactory(name="CutApOk", success_level=1)):
            cut_gem(gem_instance=gem, crafter_character=self.character, recipe=self.recipe)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 195)  # 200 - 5

    def test_unaffordable_ap_raises_before_check(self):
        self.pool.current = 2
        self.pool.save(update_fields=["current"])
        gem = self._gem()
        with self.assertRaises(CraftingCostUnaffordable):
            cut_gem(gem_instance=gem, crafter_character=self.character, recipe=self.recipe)

    def test_non_gem_rejected(self):
        with self.assertRaises(NotAGem):
            cut_gem(
                gem_instance=ItemInstanceFactory(),
                crafter_character=self.character,
                recipe=self.recipe,
            )

"""Tests for the gem value model (Build 0b slice 1)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.items.factories import (
    GemDetailsFactory,
    GemGradeFactory,
    GemInstanceDetailsFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.items.gems.constants import GemAxis
from world.items.gems.services import compute_gem_worth
from world.items.services.pricing import appraise


class GemGradeTests(TestCase):
    def test_grade_carries_axis_label_multiplier(self):
        grade = GemGradeFactory(axis=GemAxis.SIZE, label="large", multiplier=Decimal("2.5"))
        self.assertEqual(grade.axis, GemAxis.SIZE)
        self.assertEqual(grade.label, "large")
        self.assertEqual(grade.multiplier, Decimal("2.5"))


class GemDetailsTests(TestCase):
    def test_template_gem_type_accessor(self):
        ruby = ItemTemplateFactory(name="Ruby")
        self.assertIsNone(ruby.gem_type_or_none)  # not a gem type yet
        GemDetailsFactory(item_template=ruby, quality_level=6)
        ruby.refresh_from_db()
        self.assertIsNotNone(ruby.gem_type_or_none)
        self.assertEqual(ruby.gem_type_or_none.quality_level, 6)


class GemInstanceDetailsTests(TestCase):
    def test_instance_gem_accessor(self):
        inst = ItemInstanceFactory()
        self.assertIsNone(inst.gem_or_none)  # non-gem
        GemInstanceDetailsFactory(item_instance=inst)
        inst.refresh_from_db()
        self.assertIsNotNone(inst.gem_or_none)

    def test_clean_rejects_axis_mismatch(self):
        # A purity-axis grade wrongly placed in the size slot must fail validation.
        gem = GemInstanceDetailsFactory()
        gem.size_grade = GemGradeFactory(axis=GemAxis.PURITY, label="cloudy", multiplier=Decimal(1))
        with self.assertRaises(ValidationError):
            gem.clean()


class GemWorthTests(TestCase):
    def test_worth_is_product_of_base_and_three_multipliers(self):
        ruby_tmpl = ItemTemplateFactory(name="Ruby", value=100)
        gem = GemInstanceDetailsFactory(
            item_instance=ItemInstanceFactory(template=ruby_tmpl),
            size_grade=GemGradeFactory(axis=GemAxis.SIZE, label="large", multiplier=Decimal("2.0")),
            purity_grade=GemGradeFactory(
                axis=GemAxis.PURITY, label="pure", multiplier=Decimal("3.0")
            ),
            cut_grade=GemGradeFactory(axis=GemAxis.CUT, label="fine", multiplier=Decimal("1.5")),
        )
        # 100 × 2.0 × 3.0 × 1.5 = 900
        self.assertEqual(compute_gem_worth(gem), 900)

    def test_floor_grades_leave_base_unchanged(self):
        tmpl = ItemTemplateFactory(name="Common Gem", value=40)
        gem = GemInstanceDetailsFactory(
            item_instance=ItemInstanceFactory(template=tmpl),
            size_grade=GemGradeFactory(axis=GemAxis.SIZE, label="small", multiplier=Decimal("1.0")),
            purity_grade=GemGradeFactory(
                axis=GemAxis.PURITY, label="cloudy", multiplier=Decimal("1.0")
            ),
            cut_grade=GemGradeFactory(axis=GemAxis.CUT, label="uncut", multiplier=Decimal("1.0")),
        )
        self.assertEqual(compute_gem_worth(gem), 40)


class AppraiseGemBranchTests(TestCase):
    def test_appraise_uses_gem_worth_for_gems(self):
        ruby_tmpl = ItemTemplateFactory(name="Ruby", value=100)
        inst = ItemInstanceFactory(template=ruby_tmpl, lore_value=25)
        GemInstanceDetailsFactory(
            item_instance=inst,
            size_grade=GemGradeFactory(axis=GemAxis.SIZE, label="large", multiplier=Decimal("2.0")),
            purity_grade=GemGradeFactory(
                axis=GemAxis.PURITY, label="pure", multiplier=Decimal("2.0")
            ),
            cut_grade=GemGradeFactory(axis=GemAxis.CUT, label="fine", multiplier=Decimal("1.0")),
        )
        inst.refresh_from_db()
        # gem worth 100×2×2×1 = 400, plus lore_value 25
        self.assertEqual(appraise(inst), 425)

    def test_appraise_non_gem_still_uses_quality_tier(self):
        tier = QualityTierFactory(name="Fine", stat_multiplier=Decimal("2.0"))
        tmpl = ItemTemplateFactory(name="Plain Sword", value=50)
        inst = ItemInstanceFactory(template=tmpl, quality_tier=tier, lore_value=0)
        # no GemInstanceDetails → 50 × 2.0 = 100
        self.assertEqual(appraise(inst), 100)

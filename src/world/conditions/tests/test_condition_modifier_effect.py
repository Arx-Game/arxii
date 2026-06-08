"""Tests for ConditionModifierEffect (conditions setting ModifierTargets) (#636)."""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionModifierEffect
from world.conditions.services import (
    apply_condition,
    get_condition_modifier_breakdown,
    get_condition_modifier_total,
    remove_condition,
)
from world.mechanics.factories import ModifierTargetFactory


class ConditionModifierEffectModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.target = ModifierTargetFactory()

    def test_can_create_condition_level_modifier_effect(self):
        condition = ConditionTemplateFactory()
        effect = ConditionModifierEffect.objects.create(
            condition=condition, modifier_target=self.target, value=35
        )
        self.assertEqual(effect.value, 35)
        self.assertEqual(effect.modifier_target_id, self.target.pk)
        self.assertEqual(effect.get_condition_template(), condition)

    def test_factory_builds_condition_modifier_effect(self):
        effect = ConditionModifierEffectFactory(value=35)
        self.assertEqual(effect.value, 35)
        self.assertIsNotNone(effect.modifier_target_id)
        self.assertIsNotNone(effect.condition_id)
        self.assertIsNone(effect.stage)

    def test_modifier_effect_has_scales_with_severity_field(self):
        eff = ConditionModifierEffectFactory(
            condition=ConditionTemplateFactory(name="scaletest"),
            modifier_target=self.target,
            value=10,
            scales_with_severity=True,
        )
        self.assertTrue(eff.scales_with_severity)


class GetConditionModifierTotalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.target = ModifierTargetFactory()

    def test_no_active_conditions_returns_zero(self):
        self.assertEqual(get_condition_modifier_total(self.sheet, self.target), 0)

    def test_sums_active_condition_contributions(self):
        cond_a = ConditionTemplateFactory(name="modtotal_a")
        cond_b = ConditionTemplateFactory(name="modtotal_b")
        ConditionModifierEffectFactory(condition=cond_a, modifier_target=self.target, value=35)
        ConditionModifierEffectFactory(condition=cond_b, modifier_target=self.target, value=50)
        apply_condition(target=self.character, condition=cond_a)
        apply_condition(target=self.character, condition=cond_b)

        self.assertEqual(get_condition_modifier_total(self.sheet, self.target), 85)

    def test_removed_condition_stops_contributing(self):
        condition = ConditionTemplateFactory(name="modtotal_removed")
        ConditionModifierEffectFactory(condition=condition, modifier_target=self.target, value=35)
        apply_condition(target=self.character, condition=condition)
        self.assertEqual(get_condition_modifier_total(self.sheet, self.target), 35)

        remove_condition(target=self.character, condition=condition)
        self.assertEqual(get_condition_modifier_total(self.sheet, self.target), 0)


class GetConditionModifierBreakdownTests(TestCase):
    """Tests for get_condition_modifier_breakdown (#639 power ledger)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.target = ModifierTargetFactory()

    def test_no_active_conditions_returns_empty_list(self):
        """Empty list when no active conditions contribute."""
        self.assertEqual(get_condition_modifier_breakdown(self.sheet, self.target), [])

    def test_two_conditions_return_two_rows(self):
        """Two conditions each contribute one (name, value) row."""
        cond_a = ConditionTemplateFactory(name="breakdown_cond_a")
        cond_b = ConditionTemplateFactory(name="breakdown_cond_b")
        ConditionModifierEffectFactory(condition=cond_a, modifier_target=self.target, value=35)
        ConditionModifierEffectFactory(condition=cond_b, modifier_target=self.target, value=50)
        apply_condition(target=self.character, condition=cond_a)
        apply_condition(target=self.character, condition=cond_b)

        rows = get_condition_modifier_breakdown(self.sheet, self.target)
        self.assertEqual(len(rows), 2)
        names = {name for name, _ in rows}
        self.assertIn("breakdown_cond_a", names)
        self.assertIn("breakdown_cond_b", names)
        by_name = dict(rows)
        self.assertEqual(by_name["breakdown_cond_a"], 35)
        self.assertEqual(by_name["breakdown_cond_b"], 50)

    def test_staged_condition_scales_by_severity_multiplier(self):
        """A staged condition's row value reflects severity_multiplier scaling."""
        progressive = ConditionTemplateFactory(name="breakdown_staged", has_progression=True)
        stage = ConditionStageFactory(
            condition=progressive,
            stage_order=2,
            severity_multiplier=Decimal("1.5"),
        )
        ConditionModifierEffectFactory(condition=progressive, modifier_target=self.target, value=40)
        # Create active instance directly at stage 2 (severity 1.5×)
        ConditionInstanceFactory(
            target=self.character,
            condition=progressive,
            current_stage=stage,
        )

        rows = get_condition_modifier_breakdown(self.sheet, self.target)
        self.assertEqual(len(rows), 1)
        name, value = rows[0]
        self.assertEqual(name, "breakdown_staged")
        # int(40 * 1.5) == 60
        self.assertEqual(value, 60)

    def test_sum_equals_total_scenario_two_flat_conditions(self):
        """Sum of breakdown rows equals get_condition_modifier_total (flat conditions)."""
        cond_x = ConditionTemplateFactory(name="breakdown_inv_x")
        cond_y = ConditionTemplateFactory(name="breakdown_inv_y")
        ConditionModifierEffectFactory(condition=cond_x, modifier_target=self.target, value=20)
        ConditionModifierEffectFactory(condition=cond_y, modifier_target=self.target, value=30)
        apply_condition(target=self.character, condition=cond_x)
        apply_condition(target=self.character, condition=cond_y)

        rows = get_condition_modifier_breakdown(self.sheet, self.target)
        breakdown_sum = sum(v for _, v in rows)
        total = get_condition_modifier_total(self.sheet, self.target)
        self.assertEqual(breakdown_sum, total)

    def test_sum_equals_total_scenario_staged_condition(self):
        """Sum of breakdown rows equals get_condition_modifier_total (staged condition)."""
        progressive = ConditionTemplateFactory(name="breakdown_inv_staged", has_progression=True)
        stage = ConditionStageFactory(
            condition=progressive,
            stage_order=3,
            severity_multiplier=Decimal("2.0"),
        )
        ConditionModifierEffectFactory(condition=progressive, modifier_target=self.target, value=25)
        ConditionInstanceFactory(
            target=self.character,
            condition=progressive,
            current_stage=stage,
        )

        rows = get_condition_modifier_breakdown(self.sheet, self.target)
        breakdown_sum = sum(v for _, v in rows)
        total = get_condition_modifier_total(self.sheet, self.target)
        self.assertEqual(breakdown_sum, total)

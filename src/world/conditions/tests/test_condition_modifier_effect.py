"""Tests for ConditionModifierEffect (conditions setting ModifierTargets) (#636)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionModifierEffect
from world.conditions.services import (
    apply_condition,
    get_condition_modifier_total,
    remove_condition,
)
from world.mechanics.factories import ModifierTargetFactory


class ConditionModifierEffectModelTests(TestCase):
    def test_can_create_condition_level_modifier_effect(self):
        condition = ConditionTemplateFactory()
        target = ModifierTargetFactory()
        effect = ConditionModifierEffect.objects.create(
            condition=condition, modifier_target=target, value=35
        )
        self.assertEqual(effect.value, 35)
        self.assertEqual(effect.modifier_target_id, target.pk)
        self.assertEqual(effect.get_condition_template(), condition)

    def test_factory_builds_condition_modifier_effect(self):
        effect = ConditionModifierEffectFactory(value=35)
        self.assertEqual(effect.value, 35)
        self.assertIsNotNone(effect.modifier_target_id)
        self.assertIsNotNone(effect.condition_id)
        self.assertIsNone(effect.stage)


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

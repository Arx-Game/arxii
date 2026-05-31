"""Tests for ConditionModifierEffect (conditions setting ModifierTargets) (#636)."""

from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionModifierEffect
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

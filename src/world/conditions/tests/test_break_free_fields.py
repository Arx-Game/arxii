"""Tests for the break-free model fields (#2706)."""

from django.test import TestCase

from world.conditions.constants import BreakFreeMode
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory


class BreakFreeModeFieldTest(TestCase):
    def test_template_defaults_to_none_mode(self):
        template = ConditionTemplateFactory()
        self.assertEqual(template.break_free_mode, BreakFreeMode.NONE)

    def test_template_can_set_self_initiated(self):
        template = ConditionTemplateFactory(break_free_mode=BreakFreeMode.SELF_INITIATED)
        self.assertEqual(template.break_free_mode, BreakFreeMode.SELF_INITIATED)

    def test_template_can_set_periodic(self):
        template = ConditionTemplateFactory(break_free_mode=BreakFreeMode.PERIODIC)
        self.assertEqual(template.break_free_mode, BreakFreeMode.PERIODIC)

    def test_template_break_free_difficulty_default(self):
        template = ConditionTemplateFactory()
        self.assertEqual(template.break_free_difficulty, 10)

    def test_template_subtlety_default_zero(self):
        template = ConditionTemplateFactory()
        self.assertEqual(template.subtlety, 0)

    def test_template_break_free_check_type_nullable(self):
        template = ConditionTemplateFactory()
        self.assertIsNone(template.break_free_check_type)


class BreakFreeInstanceFieldsTest(TestCase):
    def test_instance_defaults_to_aware(self):
        instance = ConditionInstanceFactory()
        self.assertTrue(instance.is_aware)

    def test_instance_defaults_to_zero_rally_bonus(self):
        instance = ConditionInstanceFactory()
        self.assertEqual(instance.pending_rally_bonus, 0)

    def test_instance_can_set_unaware(self):
        instance = ConditionInstanceFactory(is_aware=False)
        self.assertFalse(instance.is_aware)

    def test_instance_can_set_rally_bonus(self):
        instance = ConditionInstanceFactory(pending_rally_bonus=15)
        self.assertEqual(instance.pending_rally_bonus, 15)

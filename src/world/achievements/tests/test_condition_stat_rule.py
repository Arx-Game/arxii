"""Tests for ConditionStatRule bridge model."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.achievements.constants import ConditionEventType
from world.achievements.factories import ConditionStatRuleFactory, StatDefinitionFactory
from world.conditions.factories import ConditionTemplateFactory


class ConditionStatRuleTests(TestCase):
    def test_unique_per_stat_condition_event(self):
        rule = ConditionStatRuleFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConditionStatRuleFactory(
                stat=rule.stat,
                condition=rule.condition,
                event_type=rule.event_type,
            )

    def test_default_increment_amount_is_one(self):
        rule = ConditionStatRuleFactory()
        self.assertEqual(rule.increment_amount, 1)

    def test_custom_increment_amount(self):
        rule = ConditionStatRuleFactory(increment_amount=5)
        self.assertEqual(rule.increment_amount, 5)

    def test_str_includes_components(self):
        stat = StatDefinitionFactory(key="conditions.singed.gained", name="Singed Gained")
        cond = ConditionTemplateFactory(name="Singed (T3 test)")
        rule = ConditionStatRuleFactory(
            stat=stat,
            condition=cond,
            event_type=ConditionEventType.GAINED,
        )
        rendered = str(rule)
        # Just assert the str representation is non-empty and references the components.
        # The exact format is up to your __str__ implementation, but it should be
        # informative enough that admin list displays read reasonably.
        self.assertTrue(rendered)
        self.assertIn("Singed", rendered)

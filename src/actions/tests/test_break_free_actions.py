"""Tests for break_free, reveal_condition, and rally actions (#2706)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.constants import BreakFreeMode
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)


class BreakFreeActionTest(TestCase):
    def setUp(self):
        self.actor = ObjectDBFactory()
        CharacterSheetFactory(character=self.actor)
        self.check_type = CheckTypeFactory()
        self.category = ConditionCategoryFactory(alters_behavior=True)
        self.template = ConditionTemplateFactory(
            category=self.category,
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=self.check_type,
        )
        self.instance = ConditionInstanceFactory(
            target=self.actor,
            condition=self.template,
            is_aware=True,
        )

    @patch("world.checks.services.perform_check")
    def test_break_free_action_success(self, mock_check):
        from actions.definitions.conditions import break_free

        mock_check.return_value = SimpleNamespace(success_level=2)
        result = break_free.run(self.actor)
        self.assertTrue(result.success)

    def test_break_free_blocked_when_no_eligible_condition(self):
        from actions.definitions.conditions import break_free

        self.template.break_free_mode = BreakFreeMode.NONE
        self.template.save(update_fields=["break_free_mode"])
        result = break_free.run(self.actor)
        self.assertFalse(result.success)

    def test_break_free_blocked_when_unaware(self):
        from actions.definitions.conditions import break_free

        self.instance.is_aware = False
        self.instance.save(update_fields=["is_aware"])
        result = break_free.run(self.actor)
        self.assertFalse(result.success)


class RevealConditionActionTest(TestCase):
    def setUp(self):
        self.target = ObjectDBFactory()
        CharacterSheetFactory(character=self.target)
        self.revealer = ObjectDBFactory()
        CharacterSheetFactory(character=self.revealer)
        self.check_type = CheckTypeFactory()
        self.category = ConditionCategoryFactory(alters_behavior=True)
        self.template = ConditionTemplateFactory(
            category=self.category,
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=self.check_type,
            subtlety=10,
        )
        self.instance = ConditionInstanceFactory(
            target=self.target,
            condition=self.template,
            is_aware=False,
        )

    @patch("world.checks.services.perform_check")
    def test_reveal_flips_awareness(self, mock_check):
        from actions.definitions.conditions import reveal_condition

        mock_check.return_value = SimpleNamespace(success_level=1)
        result = reveal_condition.run(self.revealer, target=self.target)
        self.assertTrue(result.success)
        self.instance.refresh_from_db()
        self.assertTrue(self.instance.is_aware)

    @patch("world.checks.services.perform_check")
    def test_reveal_fails_does_not_flip(self, mock_check):
        from actions.definitions.conditions import reveal_condition

        mock_check.return_value = SimpleNamespace(success_level=0)
        result = reveal_condition.run(self.revealer, target=self.target)
        self.assertFalse(result.success)
        self.instance.refresh_from_db()
        self.assertFalse(self.instance.is_aware)

    def test_reveal_no_eligible_condition(self):
        from actions.definitions.conditions import reveal_condition

        # Make the target aware — no subtle conditions to reveal.
        self.instance.is_aware = True
        self.instance.save(update_fields=["is_aware"])
        result = reveal_condition.run(self.revealer, target=self.target)
        self.assertFalse(result.success)


class RallyActionTest(TestCase):
    def setUp(self):
        self.target = ObjectDBFactory()
        CharacterSheetFactory(character=self.target)
        self.rallier = ObjectDBFactory()
        CharacterSheetFactory(character=self.rallier)
        self.check_type = CheckTypeFactory()
        self.category = ConditionCategoryFactory(alters_behavior=True)
        self.template = ConditionTemplateFactory(
            category=self.category,
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=self.check_type,
        )
        self.instance = ConditionInstanceFactory(
            target=self.target,
            condition=self.template,
            is_aware=True,
        )

    @patch("world.checks.services.perform_check")
    def test_rally_stores_bonus(self, mock_check):
        from actions.definitions.conditions import rally

        mock_check.return_value = SimpleNamespace(success_level=1)
        result = rally.run(self.rallier, target=self.target)
        self.assertTrue(result.success)
        self.instance.refresh_from_db()
        self.assertGreater(self.instance.pending_rally_bonus, 0)

    @patch("world.checks.services.perform_check")
    def test_rally_critical_triggers_immediate_break(self, mock_check):
        from actions.definitions.conditions import rally

        mock_check.return_value = SimpleNamespace(success_level=2)
        result = rally.run(self.rallier, target=self.target)
        self.assertTrue(result.success)

    @patch("world.checks.services.perform_check")
    def test_rally_failure_no_bonus(self, mock_check):
        from actions.definitions.conditions import rally

        mock_check.return_value = SimpleNamespace(success_level=0)
        result = rally.run(self.rallier, target=self.target)
        self.assertFalse(result.success)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.pending_rally_bonus, 0)

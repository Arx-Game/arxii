"""Tests for the apply-time resist-check gate on ConditionTemplate (#1738)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition, bulk_apply_conditions
from world.conditions.types import BulkConditionApplication


class ApplyConditionResistCheckTest(TestCase):
    """apply_condition consults ConditionTemplate.resist_check_type before applying."""

    def setUp(self) -> None:
        # A real typeclassed object (bare ObjectDB rows lack the ObjectParent
        # mixin — no trigger_handler — and can't exist in production).
        self.target = ObjectDBFactory(db_key="ResistTarget")
        CharacterSheetFactory(character=self.target)

    def test_resist_check_success_blocks_application(self) -> None:
        """When the target's resist roll succeeds (SL > 0), no instance is created."""
        resist_check = CheckTypeFactory()
        template = ConditionTemplateFactory(
            name="ResistibleCondition",
            resist_check_type=resist_check,
            resist_difficulty=15,
        )
        fake_result = SimpleNamespace(success_level=1)
        with patch(
            "world.conditions.services.perform_check", return_value=fake_result
        ) as mock_check:
            result = apply_condition(self.target, template)

        mock_check.assert_called_once_with(
            character=self.target,
            check_type=resist_check,
            target_difficulty=15,
        )
        self.assertFalse(result.success)
        self.assertIsNone(result.instance)
        self.assertEqual(result.message, "resisted")

    def test_resist_check_failure_allows_application(self) -> None:
        """When the target's resist roll fails (SL <= 0), the condition applies."""
        resist_check = CheckTypeFactory()
        template = ConditionTemplateFactory(
            name="ResistibleConditionFails",
            resist_check_type=resist_check,
            resist_difficulty=15,
        )
        fake_result = SimpleNamespace(success_level=0)
        with patch("world.conditions.services.perform_check", return_value=fake_result):
            result = apply_condition(self.target, template)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.instance)

    def test_null_resist_check_type_applies_unconditionally(self) -> None:
        """When resist_check_type is None (default), no check is rolled at all."""
        template = ConditionTemplateFactory(name="UnresistibleCondition")
        with patch("world.conditions.services.perform_check") as mock_check:
            result = apply_condition(self.target, template)

        mock_check.assert_not_called()
        self.assertTrue(result.success)
        self.assertIsNotNone(result.instance)


class BulkApplyConditionsResistCheckTest(TestCase):
    """bulk_apply_conditions applies the same resist-check gate per item."""

    def setUp(self) -> None:
        self.target_a = ObjectDBFactory(db_key="BulkResistTargetA")
        CharacterSheetFactory(character=self.target_a)
        self.target_b = ObjectDBFactory(db_key="BulkResistTargetB")
        CharacterSheetFactory(character=self.target_b)

    def test_one_resists_one_does_not(self) -> None:
        """Each (target, template) pair rolls its own resist check independently."""
        resist_check = CheckTypeFactory()
        template = ConditionTemplateFactory(
            name="BulkResistibleCondition",
            resist_check_type=resist_check,
            resist_difficulty=15,
        )
        # target_a resists (SL=1), target_b does not (SL=0) — SimpleNamespace side_effect
        # returns results in call order: target_a is processed first (insertion order).
        with patch(
            "world.conditions.services.perform_check",
            side_effect=[SimpleNamespace(success_level=1), SimpleNamespace(success_level=0)],
        ):
            results = bulk_apply_conditions(
                [
                    BulkConditionApplication(target=self.target_a, template=template),
                    BulkConditionApplication(target=self.target_b, template=template),
                ]
            )

        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].success)
        self.assertEqual(results[0].message, "resisted")
        self.assertTrue(results[1].success)
        self.assertIsNotNone(results[1].instance)

    def test_null_resist_check_type_applies_unconditionally_in_bulk(self) -> None:
        """A template with no resist_check_type applies normally via bulk_apply_conditions."""
        template = ConditionTemplateFactory(name="BulkUnresistibleCondition")
        with patch("world.conditions.services.perform_check") as mock_check:
            results = bulk_apply_conditions(
                [BulkConditionApplication(target=self.target_a, template=template)]
            )

        mock_check.assert_not_called()
        self.assertTrue(results[0].success)

"""Tests for the apply-time resist-check gate on ConditionTemplate (#1738)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition


class ApplyConditionResistCheckTest(TestCase):
    """apply_condition consults ConditionTemplate.resist_check_type before applying."""

    def setUp(self) -> None:
        self.target = ObjectDB.objects.create(db_key="ResistTarget")
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

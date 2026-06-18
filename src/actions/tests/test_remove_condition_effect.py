"""Tests for the remove-condition-on-check effect handler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.effects.conditions import handle_remove_condition_on_check
from actions.models import RemoveConditionOnCheckConfig
from actions.types import ActionContext, ActionResult
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import ConditionTemplateFactory


class RemoveConditionOnCheckHandlerTests(TestCase):
    """Test the remove-condition-on-check handler."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_category = CheckCategoryFactory(name="Combat")
        cls.check_type = CheckTypeFactory(
            name="restore_sense",
            category=cls.check_category,
        )
        cls.resistance_check = CheckTypeFactory(
            name="berserk_resistance",
            category=cls.check_category,
        )
        cls.berserk = ConditionTemplateFactory(name="Berserk")

    def _make_context(self) -> ActionContext:
        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=MagicMock(),
            kwargs={},
            scene_data=MagicMock(),
            result=ActionResult(success=True),
        )

    def _make_config(self, **overrides: object) -> RemoveConditionOnCheckConfig:
        defaults = {
            "check_type": self.check_type,
            "resistance_check_type": self.resistance_check,
            "condition": self.berserk,
        }
        defaults.update(overrides)
        return RemoveConditionOnCheckConfig(**defaults)

    def _successful_check_result(self) -> CheckResult:
        result = MagicMock(spec=CheckResult)
        result.success_level = 1
        return result

    def _failed_check_result(self) -> CheckResult:
        result = MagicMock(spec=CheckResult)
        result.success_level = -1
        return result

    @patch("actions.effects.conditions.remove_condition", return_value=True)
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=25)
    def test_successful_check_removes_condition(
        self,
        mock_resolve: MagicMock,
        mock_check: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        """A successful check calls remove_condition on the target."""
        mock_check.return_value = self._successful_check_result()
        context = self._make_context()
        config = self._make_config()

        handle_remove_condition_on_check(context, config)

        mock_remove.assert_called_once_with(context.target, self.berserk)

    @patch("actions.effects.conditions.remove_condition", return_value=False)
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=25)
    def test_successful_check_target_lacks_condition_is_noop(
        self,
        mock_resolve: MagicMock,
        mock_check: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        """remove_condition returning False (condition absent) is a graceful no-op."""
        mock_check.return_value = self._successful_check_result()
        context = self._make_context()
        config = self._make_config()

        # Should not raise even though remove_condition returns False
        handle_remove_condition_on_check(context, config)

        mock_remove.assert_called_once_with(context.target, self.berserk)

    @patch("actions.effects.conditions.remove_condition")
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=25)
    def test_failed_check_leaves_condition(
        self,
        mock_resolve: MagicMock,
        mock_check: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        """A failed check does NOT call remove_condition."""
        mock_check.return_value = self._failed_check_result()
        context = self._make_context()
        config = self._make_config()

        handle_remove_condition_on_check(context, config)

        mock_remove.assert_not_called()

    def test_no_target_skips_entirely(self) -> None:
        """When context.target is None, the handler exits immediately without error."""
        context = self._make_context()
        context.target = None
        config = self._make_config()

        # Should not raise
        handle_remove_condition_on_check(context, config)

    @patch("actions.effects.conditions.remove_condition", return_value=True)
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=20)
    def test_uses_fixed_difficulty_when_no_resistance_check(
        self,
        mock_resolve: MagicMock,
        mock_check: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        """Fixed target_difficulty is forwarded to resolve_target_difficulty."""
        mock_check.return_value = self._successful_check_result()
        context = self._make_context()
        config = self._make_config(resistance_check_type=None, target_difficulty=20)

        handle_remove_condition_on_check(context, config)

        mock_resolve.assert_called_once_with(context.target, None, 20)
        mock_remove.assert_called_once()

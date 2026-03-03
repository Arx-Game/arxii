"""Tests for the effects system — handlers and dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.effects.conditions import handle_condition_on_check
from actions.effects.kwargs import handle_modify_kwargs
from actions.effects.modifiers import handle_add_modifier
from actions.models import AddModifierConfig, ConditionOnCheckConfig, ModifyKwargsConfig
from actions.types import ActionContext, ActionResult
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import ConditionTemplateFactory


class ModifyKwargsHandlerTests(TestCase):
    """Test that handle_modify_kwargs transforms kwarg values."""

    def _make_context(self, **kwargs: object) -> ActionContext:
        """Build a minimal ActionContext for testing."""
        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs=dict(kwargs),
            scene_data=MagicMock(),
        )

    def test_uppercase_transform(self) -> None:
        context = self._make_context(text="hello world")
        config = ModifyKwargsConfig(
            kwarg_name="text",
            transform="uppercase",
        )
        handle_modify_kwargs(context, config)
        assert context.kwargs["text"] == "HELLO WORLD"

    def test_lowercase_transform(self) -> None:
        context = self._make_context(text="HELLO WORLD")
        config = ModifyKwargsConfig(
            kwarg_name="text",
            transform="lowercase",
        )
        handle_modify_kwargs(context, config)
        assert context.kwargs["text"] == "hello world"

    def test_missing_kwarg_is_ignored(self) -> None:
        context = self._make_context(other="value")
        config = ModifyKwargsConfig(
            kwarg_name="text",
            transform="uppercase",
        )
        handle_modify_kwargs(context, config)
        assert "text" not in context.kwargs
        assert context.kwargs["other"] == "value"

    def test_non_string_value_is_ignored(self) -> None:
        context = self._make_context(text=42)
        config = ModifyKwargsConfig(
            kwarg_name="text",
            transform="uppercase",
        )
        handle_modify_kwargs(context, config)
        assert context.kwargs["text"] == 42


class AddModifierHandlerTests(TestCase):
    """Test that handle_add_modifier sets context.modifiers values."""

    def _make_context(self) -> ActionContext:
        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs={},
            scene_data=MagicMock(),
        )

    def test_adds_modifier_to_context(self) -> None:
        context = self._make_context()
        config = AddModifierConfig(modifier_key="check_bonus", modifier_value=5)
        handle_add_modifier(context, config)
        assert context.modifiers["check_bonus"] == 5

    def test_overwrites_existing_modifier(self) -> None:
        context = self._make_context()
        context.modifiers["check_bonus"] = 3
        config = AddModifierConfig(modifier_key="check_bonus", modifier_value=10)
        handle_add_modifier(context, config)
        assert context.modifiers["check_bonus"] == 10


class ConditionOnCheckHandlerTests(TestCase):
    """Test the generic apply-condition-on-check handler."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_category = CheckCategoryFactory(name="Social")
        cls.attack_check = CheckTypeFactory(
            name="charm_attack",
            category=cls.check_category,
        )
        cls.defense_check = CheckTypeFactory(
            name="charm_defense",
            category=cls.check_category,
        )
        cls.charmed = ConditionTemplateFactory(name="Charmed")
        cls.charm_immunity = ConditionTemplateFactory(name="Charm Immunity")

    def _make_context(self) -> ActionContext:
        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=MagicMock(),
            kwargs={},
            scene_data=MagicMock(),
            result=ActionResult(success=True),
        )

    def _make_config(self, **overrides: object) -> ConditionOnCheckConfig:
        defaults = {
            "check_type": self.attack_check,
            "resistance_check_type": self.defense_check,
            "condition": self.charmed,
            "severity": 2,
            "duration_rounds": 5,
            "immunity_condition": self.charm_immunity,
            "immunity_duration": 3,
            "source_description": "Alluring Whisper",
        }
        defaults.update(overrides)
        return ConditionOnCheckConfig(**defaults)

    def _successful_check_result(self) -> CheckResult:
        """A CheckResult where success_level > 0."""
        result = MagicMock(spec=CheckResult)
        result.success_level = 1
        return result

    def _failed_check_result(self) -> CheckResult:
        """A CheckResult where success_level <= 0."""
        result = MagicMock(spec=CheckResult)
        result.success_level = -1
        return result

    @patch("actions.effects.conditions.has_condition", return_value=False)
    @patch("actions.effects.conditions.apply_condition")
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=30)
    def test_successful_check_applies_condition(
        self,
        mock_resolve: MagicMock,
        mock_check: MagicMock,
        mock_apply: MagicMock,
        mock_immune: MagicMock,
    ) -> None:
        mock_check.return_value = self._successful_check_result()
        mock_apply.return_value = MagicMock(success=True)
        context = self._make_context()
        config = self._make_config()

        handle_condition_on_check(context, config)

        mock_apply.assert_called_once_with(
            context.target,
            self.charmed,
            severity=2,
            duration_rounds=5,
            source_character=context.actor,
            source_description="Alluring Whisper",
        )

    @patch("actions.effects.conditions.has_condition", return_value=False)
    @patch("actions.effects.conditions.apply_condition")
    @patch("actions.effects.conditions.apply_immunity_on_fail")
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=30)
    def test_failed_check_applies_immunity(
        self,
        mock_resolve: MagicMock,
        mock_check: MagicMock,
        mock_immunity: MagicMock,
        mock_apply: MagicMock,
        mock_immune: MagicMock,
    ) -> None:
        mock_check.return_value = self._failed_check_result()
        context = self._make_context()
        config = self._make_config()

        handle_condition_on_check(context, config)

        mock_apply.assert_not_called()
        mock_immunity.assert_called_once_with(
            context.target,
            self.charm_immunity,
            3,
        )

    @patch("actions.effects.conditions.has_condition", return_value=True)
    @patch("actions.effects.conditions.perform_check")
    def test_immune_target_skips_check(
        self,
        mock_check: MagicMock,
        mock_immune: MagicMock,
    ) -> None:
        context = self._make_context()
        config = self._make_config()

        handle_condition_on_check(context, config)

        mock_check.assert_not_called()

    @patch("actions.effects.conditions.has_condition", return_value=False)
    @patch("actions.effects.conditions.apply_condition")
    @patch("actions.effects.conditions.perform_check")
    @patch("actions.effects.conditions.resolve_target_difficulty", return_value=30)
    def test_no_immunity_condition_skips_immunity_on_fail(
        self,
        mock_resolve: MagicMock,
        mock_check: MagicMock,
        mock_apply: MagicMock,
        mock_immune: MagicMock,
    ) -> None:
        mock_check.return_value = self._failed_check_result()
        context = self._make_context()
        config = self._make_config(immunity_condition=None)

        handle_condition_on_check(context, config)

        mock_apply.assert_not_called()

    def test_no_target_skips_entirely(self) -> None:
        context = self._make_context()
        context.target = None
        config = self._make_config()

        # Should not raise
        handle_condition_on_check(context, config)


class ApplyEffectsDispatchTests(TestCase):
    """Test that apply_effects queries configs and dispatches to handlers."""

    def _make_context(self, **kwargs: object) -> ActionContext:
        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=None,
            kwargs=dict(kwargs),
            scene_data=MagicMock(),
        )

    def _mock_manager(self, configs: list[object]) -> MagicMock:
        """Create a mock related manager that returns configs from .all()."""
        manager = MagicMock()
        manager.all.return_value = configs
        return manager

    def test_dispatches_modify_kwargs_config(self) -> None:
        from actions.effects.registry import apply_effects

        context = self._make_context(text="hello")
        config = ModifyKwargsConfig(kwarg_name="text", transform="uppercase", execution_order=0)
        enhancement = MagicMock()
        enhancement.modifykwargsconfig_configs = self._mock_manager([config])
        enhancement.addmodifierconfig_configs = self._mock_manager([])
        enhancement.conditiononcheckconfig_configs = self._mock_manager([])

        apply_effects(enhancement, context)

        assert context.kwargs["text"] == "HELLO"

    def test_dispatches_add_modifier_config(self) -> None:
        from actions.effects.registry import apply_effects

        context = self._make_context()
        config = AddModifierConfig(modifier_key="check_bonus", modifier_value=5, execution_order=0)
        enhancement = MagicMock()
        enhancement.modifykwargsconfig_configs = self._mock_manager([])
        enhancement.addmodifierconfig_configs = self._mock_manager([config])
        enhancement.conditiononcheckconfig_configs = self._mock_manager([])

        apply_effects(enhancement, context)

        assert context.modifiers["check_bonus"] == 5

    def test_respects_execution_order_across_config_types(self) -> None:
        """Configs from different tables are interleaved by execution_order."""
        from actions.effects.registry import apply_effects

        context = self._make_context(text="hello")
        modifier_config = AddModifierConfig(
            modifier_key="bonus", modifier_value=10, execution_order=0
        )
        kwargs_config = ModifyKwargsConfig(
            kwarg_name="text", transform="uppercase", execution_order=1
        )

        enhancement = MagicMock()
        enhancement.modifykwargsconfig_configs = self._mock_manager([kwargs_config])
        enhancement.addmodifierconfig_configs = self._mock_manager([modifier_config])
        enhancement.conditiononcheckconfig_configs = self._mock_manager([])

        apply_effects(enhancement, context)

        # Both effects applied
        assert context.modifiers["bonus"] == 10
        assert context.kwargs["text"] == "HELLO"

    def test_no_configs_is_noop(self) -> None:
        from actions.effects.registry import apply_effects

        context = self._make_context(text="hello")
        enhancement = MagicMock()
        enhancement.modifykwargsconfig_configs = self._mock_manager([])
        enhancement.addmodifierconfig_configs = self._mock_manager([])
        enhancement.conditiononcheckconfig_configs = self._mock_manager([])

        apply_effects(enhancement, context)

        assert context.kwargs["text"] == "hello"
        assert context.modifiers == {}

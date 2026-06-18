"""Tests for RestoreSenseAction — talk a berserk ally down (#567 Task 9).

Covers:
1. A target WITH the Berserk condition, after a successful Restore-to-Sense
   check, no longer has Berserk (remove_condition is called).
2. A non-Berserk target is a graceful no-op (remove_condition not called,
   no exception raised).
3. RestoreSenseAction is registered in the social-action registry.
4. RestoreToSenseActionTemplateFactory seeds the ActionTemplate + wires
   RemoveConditionOnCheckConfig via an ActionEnhancement.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.social import RestoreSenseAction
from actions.effects.registry import apply_effects
from actions.models import ActionEnhancement, RemoveConditionOnCheckConfig
from actions.registry import get_action
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.magic.factories import (
    BerserkConditionTemplateFactory,
    RestoreToSenseActionTemplateFactory,
)


class RestoreSenseActionRegistryTest(TestCase):
    """RestoreSenseAction is present in the registry with the expected interface."""

    def test_registered_with_correct_key(self) -> None:
        action = get_action("restore_sense")
        self.assertIsNotNone(action, "restore_sense not in registry")

    def test_target_kind_is_persona(self) -> None:
        from actions.constants import TargetKind

        action = get_action("restore_sense")
        assert action is not None
        self.assertEqual(action.target_kind, TargetKind.PERSONA)

    def test_template_name(self) -> None:
        action = get_action("restore_sense")
        assert action is not None
        self.assertIsInstance(action, RestoreSenseAction)
        self.assertEqual(action.template_name, "Restore to Sense")


class RestoreToSenseFactoryTest(TestCase):
    """RestoreToSenseActionTemplateFactory seeds the wiring correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.berserk = BerserkConditionTemplateFactory()
        cls.check_cat = CheckCategoryFactory(name="Social")
        cls.check_type = CheckTypeFactory(name="Willpower", category=cls.check_cat)
        cls.restore_content = RestoreToSenseActionTemplateFactory(check_type=cls.check_type)

    def test_action_template_created(self) -> None:
        from actions.models import ActionTemplate

        template = ActionTemplate.objects.get(name="Restore to Sense")
        self.assertEqual(template.category, "social")

    def test_action_enhancement_wired(self) -> None:
        enhs = ActionEnhancement.objects.filter(base_action_key="restore_sense")
        self.assertTrue(enhs.exists(), "No ActionEnhancement for restore_sense")

    def test_remove_condition_config_points_at_berserk(self) -> None:
        enh = ActionEnhancement.objects.filter(base_action_key="restore_sense").first()
        self.assertIsNotNone(enh)
        config = RemoveConditionOnCheckConfig.objects.filter(enhancement=enh).first()
        self.assertIsNotNone(config, "No RemoveConditionOnCheckConfig on enhancement")
        self.assertEqual(config.condition, self.berserk)


class RestoreSenseActionEffectTest(TestCase):
    """End-to-end: effect dispatch removes Berserk on check success, no-op otherwise."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.berserk = BerserkConditionTemplateFactory()
        cls.check_cat = CheckCategoryFactory(name="Social")
        cls.check_type = CheckTypeFactory(name="Willpower", category=cls.check_cat)
        cls.restore_content = RestoreToSenseActionTemplateFactory(check_type=cls.check_type)

    def _make_context(self, *, target: object = None) -> object:
        """Build a minimal ActionContext for effect dispatch."""
        from actions.types import ActionContext, ActionResult

        return ActionContext(
            action=MagicMock(),
            actor=MagicMock(),
            target=target,
            kwargs={},
            scene_data=MagicMock(),
            result=ActionResult(success=True),
        )

    def test_successful_check_removes_berserk_from_target(self) -> None:
        """Berserk target + successful check → remove_condition called."""
        target = MagicMock()
        context = self._make_context(target=target)

        successful_check = MagicMock()
        successful_check.success_level = 1

        with (
            patch("actions.effects.conditions.resolve_target_difficulty", return_value=15),
            patch("actions.effects.conditions.perform_check", return_value=successful_check),
            patch("actions.effects.conditions.remove_condition", return_value=True) as mock_remove,
        ):
            enh = ActionEnhancement.objects.filter(base_action_key="restore_sense").first()
            self.assertIsNotNone(enh)
            apply_effects(enh, context)

        mock_remove.assert_called_once_with(target, self.berserk)

    def test_failed_check_does_not_remove_berserk(self) -> None:
        """Berserk target + failed check → remove_condition NOT called."""
        target = MagicMock()
        context = self._make_context(target=target)

        failed_check = MagicMock()
        failed_check.success_level = -1

        with (
            patch("actions.effects.conditions.resolve_target_difficulty", return_value=15),
            patch("actions.effects.conditions.perform_check", return_value=failed_check),
            patch("actions.effects.conditions.remove_condition") as mock_remove,
        ):
            enh = ActionEnhancement.objects.filter(base_action_key="restore_sense").first()
            self.assertIsNotNone(enh)
            apply_effects(enh, context)

        mock_remove.assert_not_called()

    def test_non_berserk_target_is_graceful_noop(self) -> None:
        """Non-Berserk target: remove_condition returns False; no exception."""
        target = MagicMock()
        context = self._make_context(target=target)

        successful_check = MagicMock()
        successful_check.success_level = 1

        with (
            patch("actions.effects.conditions.resolve_target_difficulty", return_value=15),
            patch("actions.effects.conditions.perform_check", return_value=successful_check),
            patch("actions.effects.conditions.remove_condition", return_value=False) as mock_remove,
        ):
            enh = ActionEnhancement.objects.filter(base_action_key="restore_sense").first()
            self.assertIsNotNone(enh)
            # Should not raise even though condition is absent
            apply_effects(enh, context)

        mock_remove.assert_called_once_with(target, self.berserk)

    def test_no_target_skips_entirely(self) -> None:
        """When context.target is None, handler exits without calling remove_condition."""
        context = self._make_context(target=None)

        with patch("actions.effects.conditions.remove_condition") as mock_remove:
            enh = ActionEnhancement.objects.filter(base_action_key="restore_sense").first()
            self.assertIsNotNone(enh)
            apply_effects(enh, context)

        mock_remove.assert_not_called()

"""Tests for resolve_scene_action with ActionTemplate-based resolution."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.models.action_templates import ActionTemplate
from actions.services import resolve_scene_action
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory


class TestResolveSceneAction(TestCase):
    """resolve_scene_action uses ActionTemplate.check_type FK for real checks."""

    @classmethod
    def setUpTestData(cls) -> None:
        social_cat = CheckCategoryFactory(name="Social")
        cls.intimidation_ct = CheckTypeFactory(name="Intimidation", category=social_cat)
        cls.template = ActionTemplate.objects.create(
            name="Intimidate",
            check_type=cls.intimidation_ct,
            consequence_pool=None,
            target_type="single",
            icon="skull",
            category="social",
        )

    def test_none_template_returns_failure(self) -> None:
        character = MagicMock()
        result = resolve_scene_action(
            character=character,
            action_template=None,
            action_key="intimidate",
            difficulty=45,
        )
        assert result.success is False
        assert "No action template" in (result.message or "")

    @patch("actions.services.perform_check")
    def test_calls_perform_check_via_template_fk(self, mock_check: MagicMock) -> None:
        """Uses the ActionTemplate's check_type FK, not a string lookup."""
        mock_result = MagicMock()
        mock_result.outcome_name = "Marginal Success"
        mock_result.success_level = 1
        mock_check.return_value = mock_result

        character = MagicMock()
        result = resolve_scene_action(
            character=character,
            action_template=self.template,
            action_key="intimidate",
            difficulty=45,
        )

        mock_check.assert_called_once_with(character, self.intimidation_ct, target_difficulty=45)
        assert result.success is True
        assert result.check_outcome == "Marginal Success"
        assert result.action_key == "intimidate"

    @patch("actions.services.perform_check")
    def test_failure_based_on_success_level(self, mock_check: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.outcome_name = "Critical Failure"
        mock_result.success_level = -1
        mock_check.return_value = mock_result

        character = MagicMock()
        result = resolve_scene_action(
            character=character,
            action_template=self.template,
            action_key="intimidate",
            difficulty=45,
        )
        assert result.success is False
        assert result.check_outcome == "Critical Failure"

    @patch("actions.services.perform_check")
    def test_message_includes_template_name_and_outcome(self, mock_check: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.outcome_name = "Success"
        mock_result.success_level = 1
        mock_check.return_value = mock_result

        character = MagicMock()
        result = resolve_scene_action(
            character=character,
            action_template=self.template,
            action_key="intimidate",
            difficulty=45,
        )
        assert "Intimidate" in (result.message or "")
        assert "Success" in (result.message or "")

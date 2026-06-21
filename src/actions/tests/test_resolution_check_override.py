"""Tests for the check_type override seam in the action resolver (Task 4).

Verifies that start_action_resolution / _run_main_step honour an optional
check_type override for the immediate (SINGLE pipeline) main step, and fall
back to template.check_type when no override is supplied.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import Pipeline, ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.services import start_action_resolution
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.types import ResolutionContext


class CheckOverrideTests(TestCase):
    """Verify the check_type override param is honoured on the SINGLE pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        category = CheckCategoryFactory(name="OverrideCat")
        cls.template_check = CheckTypeFactory(name="TemplateCheck", category=category)
        cls.override_check = CheckTypeFactory(name="CasterOverrideCheck", category=category)
        cls.template = ActionTemplateFactory(
            name="Override Test Template",
            pipeline=Pipeline.SINGLE,
            check_type=cls.template_check,
            consequence_pool=None,
        )

    @patch("actions.services.perform_check")
    def test_override_check_type_used_when_provided(self, mock_perform_check: MagicMock) -> None:
        """When check_type is provided, the override check_type is rolled."""
        from world.checks.types import CheckResult

        fake_result = MagicMock(spec=CheckResult)
        fake_result.check_type = self.override_check
        fake_result.outcome = None
        mock_perform_check.return_value = fake_result

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        result = start_action_resolution(
            character, self.template, 10, context, check_type=self.override_check
        )

        assert result.current_phase == ResolutionPhase.COMPLETE
        assert result.main_result is not None

        # Verify perform_check was called with the OVERRIDE check type, not template.check_type
        call_args = mock_perform_check.call_args
        used_check_type = call_args[0][1]  # positional arg 1: check_type
        assert used_check_type is self.override_check, (
            f"Expected override check type {self.override_check!r} "
            f"but perform_check was called with {used_check_type!r}"
        )
        assert used_check_type is not self.template_check, (
            "perform_check should NOT have used template.check_type when override was provided"
        )

    @patch("actions.services.perform_check")
    def test_template_check_type_used_when_no_override(self, mock_perform_check: MagicMock) -> None:
        """When no check_type override is provided, template.check_type is used."""
        from world.checks.types import CheckResult

        fake_result = MagicMock(spec=CheckResult)
        fake_result.check_type = self.template_check
        fake_result.outcome = None
        mock_perform_check.return_value = fake_result

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        result = start_action_resolution(character, self.template, 10, context)

        assert result.current_phase == ResolutionPhase.COMPLETE
        assert result.main_result is not None

        # Verify perform_check was called with template.check_type
        call_args = mock_perform_check.call_args
        used_check_type = call_args[0][1]  # positional arg 1: check_type
        assert used_check_type is self.template_check, (
            f"Expected template check type {self.template_check!r} "
            f"but perform_check was called with {used_check_type!r}"
        )

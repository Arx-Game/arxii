"""Tests for resist-check-gated stage advancement via HOLD_OVERFLOW (Scope 7 Phase 3.2)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import advance_condition_severity
from world.conditions.types import AdvancementOutcome, AdvancementResistFailureKind


def _make_check_result(success_level: int):
    """Build a mock CheckResult whose success_level property returns the given integer."""
    result = MagicMock()
    result.success_level = success_level
    return result


class TestAdvanceConditionSeverityResistCheck(TestCase):
    """advance_condition_severity with HOLD_OVERFLOW stages."""

    def setUp(self):
        """Set up a progressive condition with two stages (severity-threshold-based)."""
        self.condition = ConditionTemplateFactory(has_progression=True)
        self.stage1 = ConditionStageFactory(
            condition=self.condition,
            stage_order=1,
            name="Stage 1",
            severity_threshold=5,
            advancement_resist_failure_kind=AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD,
            resist_check_type=None,
        )
        self.check_type = CheckTypeFactory()
        self.stage2 = ConditionStageFactory(
            condition=self.condition,
            stage_order=2,
            name="Stage 2",
            severity_threshold=10,
            advancement_resist_failure_kind=AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD,
            resist_check_type=None,
        )
        self.instance = ConditionInstanceFactory(
            condition=self.condition,
            current_stage=self.stage1,
            severity=7,
        )

    def test_advance_at_threshold_outcome(self):
        """Default ADVANCE_AT_THRESHOLD: stage advances with no resist check."""
        # severity 7 + 5 = 12, crossing stage2 threshold of 10
        result = advance_condition_severity(self.instance, 5)
        self.assertEqual(result.outcome, AdvancementOutcome.ADVANCED)
        self.assertTrue(result.stage_changed)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_stage, self.stage2)

    def test_hold_overflow_no_resist_check_type_advances(self):
        """HOLD_OVERFLOW with resist_check_type=None falls through to advancement."""
        self.stage2.advancement_resist_failure_kind = AdvancementResistFailureKind.HOLD_OVERFLOW
        self.stage2.resist_check_type = None
        self.stage2.save(update_fields=["advancement_resist_failure_kind", "resist_check_type"])

        result = advance_condition_severity(self.instance, 5)
        self.assertEqual(result.outcome, AdvancementOutcome.ADVANCED)
        self.assertTrue(result.stage_changed)

    @patch("world.conditions.services.perform_check")
    def test_hold_overflow_with_resist_check_holds_on_pass(self, mock_perform_check):
        """HOLD_OVERFLOW + resist check passes → outcome=HELD, stage unchanged."""
        self.stage2.advancement_resist_failure_kind = AdvancementResistFailureKind.HOLD_OVERFLOW
        self.stage2.resist_check_type = self.check_type
        self.stage2.save(update_fields=["advancement_resist_failure_kind", "resist_check_type"])

        mock_perform_check.return_value = _make_check_result(success_level=1)  # >= 0 = pass

        result = advance_condition_severity(self.instance, 5)

        self.assertEqual(result.outcome, AdvancementOutcome.HELD)
        self.assertFalse(result.stage_changed)
        self.assertEqual(result.new_stage, self.stage1)
        # Severity still accumulated
        self.assertEqual(result.total_severity, 12)
        # Stage should not have changed in DB
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_stage, self.stage1)

    @patch("world.conditions.services.perform_check")
    def test_hold_overflow_with_resist_check_advances_on_fail(self, mock_perform_check):
        """HOLD_OVERFLOW + resist check fails → outcome=ADVANCED."""
        self.stage2.advancement_resist_failure_kind = AdvancementResistFailureKind.HOLD_OVERFLOW
        self.stage2.resist_check_type = self.check_type
        self.stage2.save(update_fields=["advancement_resist_failure_kind", "resist_check_type"])

        mock_perform_check.return_value = _make_check_result(success_level=-1)  # < 0 = fail

        result = advance_condition_severity(self.instance, 5)

        self.assertEqual(result.outcome, AdvancementOutcome.ADVANCED)
        self.assertTrue(result.stage_changed)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_stage, self.stage2)

    def test_no_change_outcome_when_severity_below_threshold(self):
        """Severity increment doesn't cross any higher threshold → outcome=NO_CHANGE."""
        # instance is at stage1 (threshold 5, sev 7), stage2 at threshold 10
        # Add 1 → sev 8, still below stage2 threshold 10, still above stage1 threshold 5
        # new_stage query finds stage1 (threshold 5 <= 8) but stage1 == current_stage, so no change
        result = advance_condition_severity(self.instance, 1)
        self.assertEqual(result.outcome, AdvancementOutcome.NO_CHANGE)
        self.assertFalse(result.stage_changed)
        self.assertEqual(result.total_severity, 8)

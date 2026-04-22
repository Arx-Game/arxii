"""End-to-end tests for perform_treatment PENDING_ALTERATION branch (Scope 6 §9.1).

Tests the Mage Scar treatment path via reduce_pending_alteration_tier.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.constants import TreatmentTargetKind
from world.conditions.exceptions import TreatmentAlreadyAttempted
from world.conditions.factories import (
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import perform_treatment
from world.magic.constants import PendingAlterationStatus
from world.magic.factories import PendingAlterationFactory
from world.magic.models import MagicalAlterationEvent
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory


def _make_check_result(success_level: int):
    """Build a mock CheckResult with a real CheckOutcome row."""
    outcome = CheckOutcomeFactory(
        name=f"Outcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


def _make_pending_treatment(  # noqa: PLR0913 — kw-only test scaffold mirrors TreatmentTemplateFactory shape
    reduction_on_success: int = 1,
    reduction_on_crit: int = 2,
    reduction_on_partial: int = 0,
    reduction_on_failure: int = 0,
    backlash_severity_on_failure: int = 0,
    backlash_target_condition=None,
    once_per_scene_per_helper: bool = True,
):
    """Build a TreatmentTemplate targeting PENDING_ALTERATION."""
    return TreatmentTemplateFactory(
        target_kind=TreatmentTargetKind.PENDING_ALTERATION,
        target_condition=ConditionTemplateFactory(),
        check_type=CheckTypeFactory(),
        requires_bond=False,
        scene_required=False,
        once_per_scene_per_helper=once_per_scene_per_helper,
        reduction_on_crit=reduction_on_crit,
        reduction_on_success=reduction_on_success,
        reduction_on_partial=reduction_on_partial,
        reduction_on_failure=reduction_on_failure,
        backlash_severity_on_failure=backlash_severity_on_failure,
        backlash_target_condition=backlash_target_condition,
    )


class MageScarTreatmentSuccessTests(TestCase):
    """Success path: tier is reduced via reduce_pending_alteration_tier."""

    @patch("world.checks.services.perform_check")
    def test_success_on_tier_3_pending_reduces_via_reduce_pending_alteration_tier(self, mock_check):
        """Success on tier-3 pending → tier decremented, not resolved."""
        mock_check.return_value = _make_check_result(success_level=1)

        helper_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        scene = SceneFactory(is_active=True)
        pending = PendingAlterationFactory(tier=3, character=target_sheet)
        treatment = _make_pending_treatment(reduction_on_success=1)

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=pending,
        )

        pending.refresh_from_db()
        self.assertEqual(pending.tier, 2)
        self.assertEqual(result.tiers_reduced, 1)
        self.assertFalse(result.target_resolved)

    @patch("world.checks.services.perform_check")
    def test_tier_reaches_zero_marks_resolved_and_no_alteration_event(self, mock_check):
        """Tier drops to 0 → RESOLVED, resolved_alteration=None, no MagicalAlterationEvent."""
        mock_check.return_value = _make_check_result(success_level=1)

        helper_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        scene = SceneFactory(is_active=True)
        pending = PendingAlterationFactory(tier=1, character=target_sheet)
        treatment = _make_pending_treatment(reduction_on_success=1)
        event_count_before = MagicalAlterationEvent.objects.count()

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=pending,
        )

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingAlterationStatus.RESOLVED)
        self.assertIsNone(pending.resolved_alteration)
        self.assertTrue(result.target_resolved)
        # No MagicalAlterationEvent must be created (no alteration was applied)
        self.assertEqual(MagicalAlterationEvent.objects.count(), event_count_before)


class MageScarTreatmentFailureTests(TestCase):
    """Failure path: backlash is applied to helper, pending tier unchanged."""

    @patch("world.checks.services.perform_check")
    def test_failure_backlash_adds_soulfray_severity_to_helper(self, mock_check):
        """On failure, backlash condition is applied to helper; pending tier unchanged."""
        mock_check.return_value = _make_check_result(success_level=-1)

        soulfray = ConditionTemplateFactory(name=f"Soulfray_msr_{id(object())}")
        helper_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        scene = SceneFactory(is_active=True)
        pending = PendingAlterationFactory(tier=2, character=target_sheet)
        treatment = _make_pending_treatment(
            reduction_on_failure=0,
            backlash_severity_on_failure=1,
            backlash_target_condition=soulfray,
        )

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=pending,
        )

        pending.refresh_from_db()
        # Pending tier is unchanged on failure
        self.assertEqual(pending.tier, 2)
        self.assertEqual(pending.status, PendingAlterationStatus.OPEN)
        self.assertFalse(result.target_resolved)
        self.assertEqual(result.helper_backlash_applied, 1)

        # Helper gained a soulfray condition instance
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=helper_sheet.character,
                condition=soulfray,
            ).exists()
        )


class MageScarTreatmentConcurrencyTests(TestCase):
    """Unique constraint surfaces TreatmentAlreadyAttempted on duplicate insert."""

    @patch("world.checks.services.perform_check")
    def test_concurrency_two_simultaneous_helpers_raises_treatment_already_attempted(
        self, mock_check
    ):
        """Covers the race-to-insert path without requiring actual threading.

        The unique constraint fires on the second INSERT regardless of whether
        it's concurrent or sequential — Option A per plan.
        """
        mock_check.return_value = _make_check_result(success_level=1)

        helper_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        scene = SceneFactory(is_active=True)
        treatment = _make_pending_treatment(
            reduction_on_success=1,
            once_per_scene_per_helper=True,
        )
        pending1 = PendingAlterationFactory(tier=3, character=target_sheet)
        pending2 = PendingAlterationFactory(tier=3, character=target_sheet)

        # First helper succeeds
        perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=pending1,
        )

        # Same helper tries again in the same scene — unique constraint fires
        with self.assertRaises(TreatmentAlreadyAttempted):
            perform_treatment(
                helper_sheet=helper_sheet,
                target_sheet=target_sheet,
                scene=scene,
                treatment=treatment,
                target_effect=pending2,
            )

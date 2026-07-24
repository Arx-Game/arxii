"""Tests for the technique-cast treatment dispatch service (#2668).

Tests apply_technique_treatments — the sibling of apply_technique_conditions
and remove_technique_conditions that routes technique casts into
perform_treatment's bounded-mend machinery.
"""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.constants import TreatmentTargetKind
from world.conditions.exceptions import TreatmentAlreadyAttempted
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.models import TreatmentAttempt
from world.conditions.services import perform_treatment
from world.magic.factories import (
    CharacterAnimaFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import (
    ConditionTargetKind,
    TechniqueTreatment,
)
from world.magic.services.condition_application import apply_technique_treatments
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory


def _make_check_result(success_level: int):
    """Build a mock CheckResult with a real CheckOutcome row."""
    result = type("MockResult", (), {})()
    result.outcome = CheckOutcomeFactory(
        name=f"Outcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result.success_level = success_level
    return result


class ApplyTechniqueTreatmentsTest(TestCase):
    """Unit tests for apply_technique_treatments dispatch logic."""

    def setUp(self):
        self.caster_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.caster = self.caster_sheet.character
        self.target = self.target_sheet.character
        self.scene = SceneFactory(is_active=True)

        # A condition template the treatment targets.
        self.condition_template = ConditionTemplateFactory(name="Wound_TT")
        # A treatment template that reduces the condition's severity.
        self.treatment_template = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=self.condition_template,
            scene_required=False,
            once_per_scene_per_helper=False,
            check_type=CheckTypeFactory(),
            reduction_on_crit=2,
            reduction_on_success=1,
            reduction_on_partial=1,
        )
        # A technique with a treatment payload row.
        self.technique = TechniqueFactory()
        self.treatment_row = TechniqueTreatment.objects.create(
            technique=self.technique,
            treatment_template=self.treatment_template,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        # Ensure the caster has anima (in case the treatment costs anima).
        CharacterAnimaFactory(character=self.caster)

    def test_no_treatment_rows_returns_empty(self):
        """A technique with no TechniqueTreatment rows returns []."""
        from world.magic.factories import TechniqueFactory

        empty_technique = TechniqueFactory()
        results = apply_technique_treatments(
            technique=empty_technique,
            success_level=3,
            targets_by_kind={},
            source_character=self.caster,
            scene=self.scene,
        )
        self.assertEqual(results, [])

    @patch("world.checks.services.perform_check")
    def test_sl_below_minimum_skips_treatment(self, mock_perform_check):
        """Success level below minimum_success_level skips the row."""
        self.treatment_row.minimum_success_level = 5
        self.treatment_row.save()

        results = apply_technique_treatments(
            technique=self.technique,
            success_level=2,
            targets_by_kind={ConditionTargetKind.ALLY: [self.target]},
            source_character=self.caster,
            scene=self.scene,
        )
        self.assertEqual(results, [])
        mock_perform_check.assert_not_called()

    def test_target_without_matching_condition_is_noop(self):
        """Target doesn't carry the treatment's target condition → no-op."""
        results = apply_technique_treatments(
            technique=self.technique,
            success_level=3,
            targets_by_kind={ConditionTargetKind.ALLY: [self.target]},
            source_character=self.caster,
            scene=self.scene,
        )
        self.assertEqual(results, [])

    @patch("world.checks.services.perform_check")
    def test_treatment_fires_on_matching_condition(self, mock_perform_check):
        """Target carries the condition → perform_treatment is called."""
        mock_perform_check.return_value = _make_check_result(success_level=2)
        ConditionInstanceFactory(
            target=self.target,
            condition=self.condition_template,
            severity=3,
        )

        results = apply_technique_treatments(
            technique=self.technique,
            success_level=3,
            targets_by_kind={ConditionTargetKind.ALLY: [self.target]},
            source_character=self.caster,
            scene=self.scene,
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].effect_applied)
        # TreatmentAttempt was recorded.
        self.assertTrue(
            TreatmentAttempt.objects.filter(
                helper=self.caster,
                target=self.target,
                treatment=self.treatment_template,
            ).exists()
        )

    @patch("world.checks.services.perform_check")
    def test_treatment_exception_caught_not_raised(self, mock_perform_check):
        """TreatmentAlreadyAttempted is caught; cast continues."""
        mock_perform_check.return_value = _make_check_result(success_level=2)
        ConditionInstanceFactory(
            target=self.target,
            condition=self.condition_template,
            severity=3,
        )

        # Patch perform_treatment at its source to raise.
        with patch(
            "world.conditions.services.perform_treatment",
            side_effect=TreatmentAlreadyAttempted("already"),
        ):
            results = apply_technique_treatments(
                technique=self.technique,
                success_level=3,
                targets_by_kind={ConditionTargetKind.ALLY: [self.target]},
                source_character=self.caster,
                scene=self.scene,
            )
        # No exception raised; empty results (treatment was caught).
        self.assertEqual(results, [])

    @patch("world.checks.services.perform_check")
    def test_skip_engagement_gate_passed_to_perform_treatment(self, mock_perform_check):
        """apply_technique_treatments passes skip_engagement_gate=True."""
        mock_perform_check.return_value = _make_check_result(success_level=2)
        ConditionInstanceFactory(
            target=self.target,
            condition=self.condition_template,
            severity=3,
        )

        with patch(
            "world.conditions.services.perform_treatment",
            wraps=perform_treatment,
        ) as mock_perform:
            apply_technique_treatments(
                technique=self.technique,
                success_level=3,
                targets_by_kind={ConditionTargetKind.ALLY: [self.target]},
                source_character=self.caster,
                scene=self.scene,
            )
            # Verify skip_engagement_gate=True was passed.
            _, kwargs = mock_perform.call_args
            self.assertTrue(kwargs.get("skip_engagement_gate"))

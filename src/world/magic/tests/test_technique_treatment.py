"""Tests for the technique-cast treatment dispatch service (#2668).

Tests apply_technique_treatments — the sibling of apply_technique_conditions
and remove_technique_conditions that routes technique casts into
perform_treatment's bounded-mend machinery.
"""

from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
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
from world.vitals.constants import NEVER_TO_FULL_FRACTION


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
        CharacterAnimaFactory(character=self.caster_sheet)

    def test_no_treatment_rows_returns_empty(self):
        """A technique with no TechniqueTreatment rows returns []."""
        from world.magic.factories import TechniqueFactory

        empty_technique = TechniqueFactory()
        results = apply_technique_treatments(
            technique=empty_technique,
            success_level=3,
            eff_intensity=5,
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
            eff_intensity=5,
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
            eff_intensity=5,
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
            eff_intensity=5,
            targets_by_kind={ConditionTargetKind.ALLY: [self.target]},
            source_character=self.caster,
            scene=self.scene,
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].effect_applied)
        # TreatmentAttempt was recorded.
        self.assertTrue(
            TreatmentAttempt.objects.filter(
                helper=self.caster_sheet,
                target=self.target_sheet,
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
                eff_intensity=5,
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
                eff_intensity=5,
                targets_by_kind={ConditionTargetKind.ALLY: [self.target]},
                source_character=self.caster,
                scene=self.scene,
            )
            # Verify skip_engagement_gate=True was passed.
            _, kwargs = mock_perform.call_args
            self.assertTrue(kwargs.get("skip_engagement_gate"))

    @patch("world.checks.services.perform_check")
    def test_eff_intensity_forwarded_as_power_intensity(self, mock_perform_check):
        """#3391 back-compat anchor: apply_technique_treatments forwards its eff_intensity
        kwarg to perform_treatment as power_intensity, across a matrix of values. This
        suite's shared treatment_template leaves mend_intensity_multiplier at the field
        default (0), so real mend amounts stay unaffected by eff_intensity regardless
        of what's forwarded — the wiring exists but has zero effect at the default.
        """
        mock_perform_check.return_value = _make_check_result(success_level=2)

        for eff_intensity in (0, 10, 100):
            with self.subTest(eff_intensity=eff_intensity):
                # A fresh condition template + instance per iteration — the shared
                # treatment_template's reduction_on_success would resolve a reused
                # instance after enough successful iterations (leaving no matching
                # target_effect for later calls), and ConditionInstance is unique per
                # (target, condition), so a fresh template avoids both problems.
                iteration_condition = ConditionTemplateFactory(
                    name=f"Wound_TT_power_{eff_intensity}"
                )
                self.treatment_template.target_condition = iteration_condition
                self.treatment_template.save(update_fields=["target_condition"])
                ConditionInstanceFactory(
                    target=self.target,
                    condition=iteration_condition,
                    severity=3,
                )
                with patch(
                    "world.conditions.services.perform_treatment",
                    wraps=perform_treatment,
                ) as mock_perform:
                    apply_technique_treatments(
                        technique=self.technique,
                        success_level=3,
                        eff_intensity=eff_intensity,
                        targets_by_kind={ConditionTargetKind.ALLY: [self.target]},
                        source_character=self.caster,
                        scene=self.scene,
                    )
                _, kwargs = mock_perform.call_args
                self.assertEqual(kwargs.get("power_intensity"), eff_intensity)


class TreatmentRowOverrideTests(TestCase):
    """#4581: the treatment_rows override and the missing-sheet skip."""

    def setUp(self) -> None:
        self.caster_sheet = CharacterSheetFactory()
        self.ally_sheet = CharacterSheetFactory()
        self.caster = self.caster_sheet.character
        self.ally = self.ally_sheet.character
        self.scene = SceneFactory(is_active=True)
        self.condition = ConditionTemplateFactory(name="Wound_Override")
        self.template = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=self.condition,
            scene_required=False,
            once_per_scene_per_helper=False,
            check_type=CheckTypeFactory(),
            reduction_on_crit=2,
            reduction_on_success=1,
            reduction_on_partial=1,
        )
        self.technique_a = TechniqueFactory()
        self.technique_b = TechniqueFactory()
        self.row_b = TechniqueTreatment.objects.create(
            technique=self.technique_b,
            treatment_template=self.template,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        CharacterAnimaFactory(character=self.caster_sheet)

    @patch("world.checks.services.perform_check")
    def test_treatment_rows_override_treats_from_the_given_rows(self, mock_check) -> None:
        mock_check.return_value = _make_check_result(success_level=2)
        ConditionInstanceFactory(target=self.ally, condition=self.condition, severity=3)
        results = apply_technique_treatments(
            technique=self.technique_a,
            success_level=3,
            eff_intensity=0,
            targets_by_kind={ConditionTargetKind.ALLY: [self.ally]},
            source_character=self.caster,
            scene=self.scene,
            treatment_rows=[self.row_b],
        )
        self.assertEqual(len(results), 1)
        attempt = TreatmentAttempt.objects.get()
        self.assertEqual(attempt.helper, self.caster_sheet)
        self.assertEqual(attempt.target, self.ally_sheet)

    def test_the_techniques_own_rows_are_ignored_under_an_override(self) -> None:
        TechniqueTreatment.objects.create(
            technique=self.technique_a,
            treatment_template=self.template,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        with patch(
            "world.magic.services.condition_application._find_treatment_target_effect"
        ) as find:
            results = apply_technique_treatments(
                technique=self.technique_a,
                success_level=3,
                eff_intensity=0,
                targets_by_kind={ConditionTargetKind.ALLY: [self.ally]},
                source_character=self.caster,
                scene=self.scene,
                treatment_rows=[],
            )
        self.assertEqual(results, [])
        find.assert_not_called()

    def test_a_target_without_a_sheet_is_skipped_not_raised(self) -> None:
        sheetless = ObjectDBFactory(db_key="SheetlessTreatmentTarget")
        results = apply_technique_treatments(
            technique=self.technique_b,
            success_level=3,
            eff_intensity=0,
            targets_by_kind={ConditionTargetKind.ALLY: [sheetless]},
            source_character=self.caster,
            scene=self.scene,
        )
        self.assertEqual(results, [])


class MendCapFractionAuthoringTests(TestCase):
    """How far one technique's treatment may heal a wound is authored on its row (#4600)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory()
        cls.template = TreatmentTemplateFactory()

    def _row(self, fraction: str) -> TechniqueTreatment:
        return TechniqueTreatment(
            technique=self.technique,
            treatment_template=self.template,
            mend_cap_fraction=Decimal(fraction),
        )

    def test_a_new_row_defaults_to_the_ceiling(self) -> None:
        row = TechniqueTreatment.objects.create(
            technique=self.technique, treatment_template=self.template
        )
        self.assertEqual(row.mend_cap_fraction, NEVER_TO_FULL_FRACTION)

    def test_the_database_refuses_full_and_none(self) -> None:
        for fraction in ("1.00", "0.00"):
            with self.subTest(fraction=fraction):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self._row(fraction).save()

    def test_clean_refuses_a_fraction_above_the_ceiling(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            self._row("0.80").full_clean()
        self.assertIn("mend_cap_fraction", caught.exception.message_dict)

    def test_clean_accepts_the_ceiling_and_below(self) -> None:
        for fraction in ("0.75", "0.40"):
            with self.subTest(fraction=fraction):
                self._row(fraction).full_clean()

    def test_the_draft_row_carries_the_same_rule_and_default(self) -> None:
        from world.magic.models import TechniqueDraft, TechniqueDraftTreatment

        draft = TechniqueDraft.objects.create(character=CharacterSheetFactory())
        row = TechniqueDraftTreatment.objects.create(draft=draft, treatment_template=self.template)
        self.assertEqual(row.mend_cap_fraction, NEVER_TO_FULL_FRACTION)
        row.mend_cap_fraction = Decimal("0.80")
        with self.assertRaises(ValidationError):
            row.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TechniqueDraftTreatment.objects.create(
                draft=draft, treatment_template=self.template, mend_cap_fraction=Decimal("1.00")
            )

    def test_the_vow_added_effect_row_carries_the_same_rule_and_default(self) -> None:
        from world.covenants.factories import VowAddedEffectTreatmentFactory

        row = VowAddedEffectTreatmentFactory(treatment_template=self.template)
        self.assertEqual(row.mend_cap_fraction, NEVER_TO_FULL_FRACTION)
        row.mend_cap_fraction = Decimal("0.80")
        with self.assertRaises(ValidationError) as caught:
            row.full_clean()
        self.assertIn("mend_cap_fraction", caught.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            VowAddedEffectTreatmentFactory(mend_cap_fraction=Decimal("0.00"))

"""Tests for wound-mend treatment integration (#2644 — double-bounded HP mend).

Exercises perform_treatment's new mend routing (mend_on_* -> mend_wound()) and
the once_per_wound_per_helper duplicate gate — independent of, and alongside,
the pre-existing once_per_scene_per_helper gate covered by
test_treatment_constraint.py / test_treatment_aftermath.py (both untouched by
this change; defaults preserve their behavior).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
from world.conditions.services import perform_treatment
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import WoundDetails


def _make_check_result(success_level: int):
    """Build a mock CheckResult with a real CheckOutcome row."""
    outcome = CheckOutcomeFactory(
        name=f"WoundOutcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


class WoundTreatmentMendTests(TestCase):
    """perform_treatment routes mend_on_* through mend_wound() (#2644)."""

    def _setup(self, *, damage_taken: int = 40, severity: int = 2, **extra_treatment_kwargs):
        helper_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=target_sheet, health=20, max_health=100)
        scene = SceneFactory(is_active=True)
        wound_template = ConditionTemplateFactory(name=f"TestWound_{id(object())}")
        treatment_kwargs = {
            "target_kind": TreatmentTargetKind.PRIMARY,
            "target_condition": wound_template,
            "check_type": CheckTypeFactory(),
            "requires_bond": False,
            "scene_required": False,
            "once_per_scene_per_helper": False,
            "once_per_wound_per_helper": True,
            "reduction_on_crit": 2,
            "reduction_on_success": 1,
            "reduction_on_partial": 1,
            "reduction_on_failure": 0,
            "mend_on_crit": 20,
            "mend_on_success": 10,
            "mend_on_partial": 5,
        }
        treatment_kwargs.update(extra_treatment_kwargs)
        treatment = TreatmentTemplateFactory(**treatment_kwargs)
        target_effect = ConditionInstanceFactory(
            target=target_sheet.character,
            condition=wound_template,
            severity=severity,
        )
        WoundDetails.objects.create(condition_instance=target_effect, damage_taken=damage_taken)
        return helper_sheet, target_sheet, scene, treatment, target_effect

    @patch("world.checks.services.perform_check")
    def test_success_mends_health_and_reduces_severity(self, mock_check) -> None:
        mock_check.return_value = _make_check_result(success_level=1)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup()

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        self.assertEqual(result.health_mended, 10)
        self.assertEqual(result.attempt.health_mended, 10)
        self.assertTrue(result.effect_applied)
        self.assertEqual(target_sheet.vitals.health, 30)
        self.assertEqual(result.severity_reduced, 1)
        target_effect.refresh_from_db()
        self.assertEqual(target_effect.severity, 1)

    @patch("world.checks.services.perform_check")
    def test_mend_capped_by_never_to_full_fraction(self, mock_check) -> None:
        # damage_taken=40 -> cap = floor(0.75 * 40) = 30. A crit's mend_on_crit
        # of 100 would blow well past both the fraction cap and max_health;
        # the fraction cap (30) binds first here since room-to-max is 80.
        mock_check.return_value = _make_check_result(success_level=2)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup(mend_on_crit=100)

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        self.assertEqual(result.health_mended, 30)
        details = WoundDetails.objects.get(condition_instance=target_effect)
        self.assertEqual(details.health_mended_total, 30)

    @patch("world.checks.services.perform_check")
    def test_failure_mends_nothing(self, mock_check) -> None:
        mock_check.return_value = _make_check_result(success_level=-1)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup()

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        self.assertEqual(result.health_mended, 0)
        self.assertEqual(target_sheet.vitals.health, 20)

    @patch("world.checks.services.perform_check")
    def test_second_tending_by_same_healer_rejected(self, mock_check) -> None:
        mock_check.return_value = _make_check_result(success_level=1)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup()

        perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )
        with self.assertRaises(TreatmentAlreadyAttempted):
            perform_treatment(
                helper_sheet=helper_sheet,
                target_sheet=target_sheet,
                scene=scene,
                treatment=treatment,
                target_effect=target_effect,
            )

    @patch("world.checks.services.perform_check")
    def test_different_healer_permitted_on_same_wound(self, mock_check) -> None:
        mock_check.return_value = _make_check_result(success_level=1)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup()
        other_helper = CharacterSheetFactory()

        perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )
        # A different healer tending the SAME wound is not blocked by the
        # once_per_wound_per_helper gate (it keys on helper, not just wound).
        second_result = perform_treatment(
            helper_sheet=other_helper,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )
        self.assertEqual(second_result.health_mended, 10)
        self.assertEqual(target_sheet.vitals.health, 40)

    @patch("world.checks.services.perform_check")
    def test_health_never_exceeds_max(self, mock_check) -> None:
        mock_check.return_value = _make_check_result(success_level=2)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup(damage_taken=1000)
        target_sheet.vitals.health = 99
        target_sheet.vitals.save(update_fields=["health"])

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        self.assertEqual(result.health_mended, 1)
        self.assertEqual(target_sheet.vitals.health, 100)

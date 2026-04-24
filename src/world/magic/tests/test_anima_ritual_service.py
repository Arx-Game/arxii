"""Service tests for perform_anima_ritual (Scope 6 Phase 8).

Tests are grouped by scenario. The _scene_participant gate is patched to
return True unless a test specifically exercises the gate. SoulfrayConfig
and ConditionTemplate rows are created in setUp because they are singletons
queried with .first() / .get(name=...).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.exceptions import (
    CharacterEngagedForRitual,
    NoRitualConfigured,
    RitualAlreadyPerformedThisScene,
    RitualScenePrerequisiteFailed,
)
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAnimaRitualFactory,
    SoulfrayConfigFactory,
)
from world.magic.models.anima import AnimaRitualPerformance
from world.magic.services.anima import perform_anima_ritual
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory


def _make_check_result(success_level: int) -> MagicMock:
    """Build a mock CheckResult with a real CheckOutcome row."""
    outcome = CheckOutcomeFactory(
        name=f"Outcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


# Patch target: source module where perform_check is defined
_PERFORM_CHECK_PATH = "world.checks.services.perform_check"
# Patch target for scene gate
_SCENE_PARTICIPANT_PATH = "world.magic.services.anima._scene_participant"


class NoRitualConfiguredTests(TestCase):
    """Gate: character has no anima_ritual configured."""

    def test_no_ritual_raises(self) -> None:
        sheet = CharacterSheetFactory()
        scene = SceneFactory(is_active=True)
        with self.assertRaises(NoRitualConfigured):
            perform_anima_ritual(character_sheet=sheet, scene=scene)


class CritNoSoulfrayTests(TestCase):
    """Crit with no active Soulfray: anima goes to max, no severity change."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = CharacterAnimaRitualFactory(character=self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet.character,
            current=3,
            maximum=10,
        )
        self.soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        self.config = SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=1,
        )
        self.scene = SceneFactory(is_active=True)

    @patch(_SCENE_PARTICIPANT_PATH, return_value=True)
    @patch(_PERFORM_CHECK_PATH)
    def test_crit_no_soulfray_anima_goes_to_max(
        self, mock_check: MagicMock, mock_scene: MagicMock
    ) -> None:
        mock_check.return_value = _make_check_result(success_level=2)

        result = perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)

        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 10)
        self.assertEqual(result.severity_reduced, 0)
        self.assertEqual(result.anima_recovered, 7)  # 10 - 3
        self.assertFalse(result.soulfray_resolved)
        self.assertIsNone(result.soulfray_stage_after)
        mock_scene.assert_called()


class CritWithSoulfrayTests(TestCase):
    """Crit with active Soulfray: severity paid down, anima goes to max."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = CharacterAnimaRitualFactory(character=self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet.character,
            current=5,
            maximum=10,
        )
        self.soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        self.soulfray_inst = ConditionInstanceFactory(
            target=self.sheet.character,
            condition=self.soulfray_template,
            severity=2,
        )
        self.config = SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=2,  # 2 budget per severity point
        )
        self.scene = SceneFactory(is_active=True)

    @patch(_SCENE_PARTICIPANT_PATH, return_value=True)
    @patch(_PERFORM_CHECK_PATH)
    def test_crit_with_soulfray_severity_paid_down_anima_force_refilled(
        self, mock_check: MagicMock, mock_scene: MagicMock
    ) -> None:
        mock_check.return_value = _make_check_result(success_level=2)

        result = perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)

        # Crit budget=10, cost_per_point=2: can reduce 5 severity points, but only 2 exist
        # After 2 reductions: budget = 10 - 4 = 6 remaining
        # Crit always fills anima to max regardless
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 10)
        self.assertEqual(result.severity_reduced, 2)
        self.assertTrue(result.soulfray_resolved)
        mock_scene.assert_called()


class SuccessWithSoulfrayTests(TestCase):
    """Success outcome with Soulfray: partial severity reduction + partial anima."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = CharacterAnimaRitualFactory(character=self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet.character,
            current=2,
            maximum=10,
        )
        self.soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        self.soulfray_inst = ConditionInstanceFactory(
            target=self.sheet.character,
            condition=self.soulfray_template,
            severity=5,  # 5 severity points
        )
        self.config = SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=2,  # 2 budget per severity point
        )
        self.scene = SceneFactory(is_active=True)

    @patch(_SCENE_PARTICIPANT_PATH, return_value=True)
    @patch(_PERFORM_CHECK_PATH)
    def test_success_with_soulfray_severity_reduced_partial_anima_refill(
        self, mock_check: MagicMock, mock_scene: MagicMock
    ) -> None:
        mock_check.return_value = _make_check_result(success_level=1)

        result = perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)

        # Success budget=6, cost_per_point=2: can reduce 3 severity points (cost=6)
        # Budget exhausted after 3 reductions → 0 left for anima
        self.assertEqual(result.severity_reduced, 3)
        self.anima.refresh_from_db()
        # budget=0 after severity reduction, so anima stays at 2
        self.assertEqual(self.anima.current, 2)
        self.assertEqual(result.anima_recovered, 0)
        self.assertFalse(result.soulfray_resolved)
        mock_scene.assert_called()


class PartialWithHighSoulfrayTests(TestCase):
    """Partial outcome with high severity Soulfray: small severity reduction, minimal anima."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = CharacterAnimaRitualFactory(character=self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet.character,
            current=1,
            maximum=10,
        )
        self.soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        self.soulfray_inst = ConditionInstanceFactory(
            target=self.sheet.character,
            condition=self.soulfray_template,
            severity=10,
        )
        self.config = SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=2,
        )
        self.scene = SceneFactory(is_active=True)

    @patch(_SCENE_PARTICIPANT_PATH, return_value=True)
    @patch(_PERFORM_CHECK_PATH)
    def test_partial_high_soulfray_small_severity_reduction_minimal_anima(
        self, mock_check: MagicMock, mock_scene: MagicMock
    ) -> None:
        mock_check.return_value = _make_check_result(success_level=0)

        result = perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)

        # Partial budget=3, cost_per_point=2:
        #   iteration 1: budget(3)>0 → reduce, budget=1
        #   iteration 2: budget(1)>0 → reduce, budget=-1
        #   loop exits (budget<=0)
        # So 2 reductions, budget=-1 (negative → max(0,-1)=0 for anima)
        self.assertEqual(result.severity_reduced, 2)
        self.anima.refresh_from_db()
        # budget<0 → max(0, budget)=0 → no anima added
        self.assertEqual(self.anima.current, 1)
        self.assertEqual(result.anima_recovered, 0)
        self.assertFalse(result.soulfray_resolved)
        mock_scene.assert_called()


class FailureNoSoulfrayTests(TestCase):
    """Failure outcome with no Soulfray: small anima refill."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = CharacterAnimaRitualFactory(character=self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet.character,
            current=0,
            maximum=10,
        )
        self.soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        self.config = SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=1,
        )
        self.scene = SceneFactory(is_active=True)

    @patch(_SCENE_PARTICIPANT_PATH, return_value=True)
    @patch(_PERFORM_CHECK_PATH)
    def test_failure_no_soulfray_small_anima_refill(
        self, mock_check: MagicMock, mock_scene: MagicMock
    ) -> None:
        mock_check.return_value = _make_check_result(success_level=-1)

        result = perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)

        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 1)  # failure budget = 1
        self.assertEqual(result.anima_recovered, 1)
        self.assertEqual(result.severity_reduced, 0)
        mock_scene.assert_called()


class GateTests(TestCase):
    """Gate conditions that raise before check is rolled."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = CharacterAnimaRitualFactory(character=self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet.character,
            current=5,
            maximum=10,
        )
        self.soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        self.config = SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=1,
        )
        self.scene = SceneFactory(is_active=True)

    @patch(_SCENE_PARTICIPANT_PATH, return_value=True)
    @patch(_PERFORM_CHECK_PATH)
    def test_engaged_character_raises(
        self,
        mock_check: MagicMock,
        mock_scene: MagicMock,  # noqa: ARG002
    ) -> None:
        CharacterEngagementFactory(character=self.sheet.character)
        with self.assertRaises(CharacterEngagedForRitual):
            perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)
        mock_check.assert_not_called()
        # engagement gate runs before scene gate, so _scene_participant is never called

    @patch(_SCENE_PARTICIPANT_PATH, return_value=True)
    @patch(_PERFORM_CHECK_PATH)
    def test_second_ritual_same_scene_raises(
        self, mock_check: MagicMock, mock_scene: MagicMock
    ) -> None:
        mock_check.return_value = _make_check_result(success_level=1)
        # First call succeeds
        perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)
        # Second call raises
        with self.assertRaises(RitualAlreadyPerformedThisScene):
            perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)
        mock_scene.assert_called()

    @patch(_PERFORM_CHECK_PATH)
    def test_scene_gate_raises_when_not_participant(self, mock_check: MagicMock) -> None:
        # _scene_participant returns False (default — no roster setup)
        with self.assertRaises(RitualScenePrerequisiteFailed):
            perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)
        mock_check.assert_not_called()


class PerformanceRowTests(TestCase):
    """Performance row is persisted with accurate fields."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = CharacterAnimaRitualFactory(character=self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet.character,
            current=3,
            maximum=10,
        )
        self.soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        self.config = SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=1,
        )
        self.scene = SceneFactory(is_active=True)

    @patch(_SCENE_PARTICIPANT_PATH, return_value=True)
    @patch(_PERFORM_CHECK_PATH)
    def test_performance_row_persisted_with_accurate_fields(
        self, mock_check: MagicMock, mock_scene: MagicMock
    ) -> None:
        mock_check.return_value = _make_check_result(success_level=1)

        result = perform_anima_ritual(character_sheet=self.sheet, scene=self.scene)

        perf = AnimaRitualPerformance.objects.get(pk=result.performance.pk)
        self.assertEqual(perf.ritual, self.ritual)
        self.assertEqual(perf.scene, self.scene)
        self.assertTrue(perf.was_successful)
        # success budget=6, no soulfray, so anima goes from 3 to 9
        self.assertEqual(perf.anima_recovered, 6)
        self.assertEqual(perf.severity_reduced, 0)
        self.assertIsNotNone(perf.outcome)
        mock_scene.assert_called()

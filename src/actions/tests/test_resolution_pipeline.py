"""Tests for the action resolution pipeline state machine."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import Pipeline, PlayerDecision, ResolutionPhase
from actions.factories import (
    ActionTemplateFactory,
    ActionTemplateGateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from actions.services import advance_resolution, start_action_resolution
from world.checks.factories import ConsequenceFactory
from world.checks.types import CheckResult, ResolutionContext
from world.traits.factories import CheckOutcomeFactory


def _make_check_result(
    outcome: object | None = None,
    success_level: int = 1,
) -> CheckResult:
    """Build a minimal CheckResult for testing."""
    if outcome is None:
        outcome = MagicMock()
        outcome.name = "Success"
        outcome.success_level = success_level
    return CheckResult(
        check_type=MagicMock(),
        outcome=outcome,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


def _make_failing_check_result() -> CheckResult:
    """Build a CheckResult that registers as a failure (success_level <= 0)."""
    outcome = MagicMock()
    outcome.name = "Failure"
    outcome.success_level = -1
    return _make_check_result(outcome=outcome)


class SinglePipelineTests(TestCase):
    """Test SINGLE pipeline resolves to COMPLETE immediately."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome = CheckOutcomeFactory(name="Hit", success_level=1)
        cls.pool = ConsequencePoolFactory(name="Single Pool")
        cls.consequence = ConsequenceFactory(outcome_tier=cls.outcome, label="Damage", weight=10)
        ConsequencePoolEntryFactory(pool=cls.pool, consequence=cls.consequence)
        cls.template = ActionTemplateFactory(
            name="Fire Bolt",
            pipeline=Pipeline.SINGLE,
            consequence_pool=cls.pool,
        )

    @patch("actions.services.apply_resolution", return_value=[])
    @patch("actions.services.select_consequence_from_result")
    @patch("actions.services.perform_check")
    def test_single_pipeline_completes(
        self,
        mock_check: MagicMock,
        mock_select: MagicMock,
        mock_apply: MagicMock,
    ) -> None:
        check_result = _make_check_result()
        mock_check.return_value = check_result

        from world.checks.types import PendingResolution

        mock_select.return_value = PendingResolution(
            check_result=check_result,
            selected_consequence=self.consequence,
        )

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        result = start_action_resolution(character, self.template, 10, context)

        assert result.current_phase == ResolutionPhase.COMPLETE
        assert result.main_result is not None
        assert result.main_result.step_label == "main"
        assert result.main_result.consequence_id == self.consequence.pk
        assert result.gate_results == []
        mock_check.assert_called_once()
        mock_apply.assert_called_once()


class GatedPipelinePassTests(TestCase):
    """Test GATED pipeline where gate passes and main resolves."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome = CheckOutcomeFactory(name="Success", success_level=1)
        cls.main_pool = ConsequencePoolFactory(name="Main Pool")
        cls.main_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome, label="Main Effect", weight=10
        )
        ConsequencePoolEntryFactory(pool=cls.main_pool, consequence=cls.main_consequence)

        cls.gate_pool = ConsequencePoolFactory(name="Gate Pool")
        cls.gate_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome, label="Gate Effect", weight=10
        )
        ConsequencePoolEntryFactory(pool=cls.gate_pool, consequence=cls.gate_consequence)

        cls.template = ActionTemplateFactory(
            name="Gated Spell",
            pipeline=Pipeline.GATED,
            consequence_pool=cls.main_pool,
        )
        cls.gate = ActionTemplateGateFactory(
            action_template=cls.template,
            consequence_pool=cls.gate_pool,
            failure_aborts=True,
            step_order=0,
        )

    @patch("actions.services.apply_resolution", return_value=[])
    @patch("actions.services.select_consequence_from_result")
    @patch("actions.services.perform_check")
    def test_gate_passes_main_resolves(
        self,
        mock_check: MagicMock,
        mock_select: MagicMock,
        mock_apply: MagicMock,
    ) -> None:
        success_result = _make_check_result()
        mock_check.return_value = success_result

        from world.checks.types import PendingResolution

        mock_select.return_value = PendingResolution(
            check_result=success_result,
            selected_consequence=self.gate_consequence,
        )

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        result = start_action_resolution(character, self.template, 10, context)

        assert result.current_phase == ResolutionPhase.COMPLETE
        assert len(result.gate_results) == 1
        assert result.gate_results[0].step_label == "gate:activation"
        assert result.main_result is not None
        assert result.main_result.step_label == "main"


class GatedPipelineAbortTests(TestCase):
    """Test GATED pipeline where gate fails with failure_aborts=True."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.main_pool = ConsequencePoolFactory(name="Main Abort Pool")
        cls.main_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome, label="Main Abort", weight=10
        )
        ConsequencePoolEntryFactory(pool=cls.main_pool, consequence=cls.main_consequence)

        cls.gate_pool = ConsequencePoolFactory(name="Gate Abort Pool")
        cls.gate_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome, label="Gate Abort", weight=10
        )
        ConsequencePoolEntryFactory(pool=cls.gate_pool, consequence=cls.gate_consequence)

        cls.template = ActionTemplateFactory(
            name="Abortable Spell",
            pipeline=Pipeline.GATED,
            consequence_pool=cls.main_pool,
        )
        cls.gate = ActionTemplateGateFactory(
            action_template=cls.template,
            consequence_pool=cls.gate_pool,
            failure_aborts=True,
            step_order=0,
        )

    @patch("actions.services.apply_resolution", return_value=[])
    @patch("actions.services.select_consequence_from_result")
    @patch("actions.services.perform_check")
    def test_gate_fails_aborts_pipeline(
        self,
        mock_check: MagicMock,
        mock_select: MagicMock,
        mock_apply: MagicMock,
    ) -> None:
        fail_result = _make_failing_check_result()
        mock_check.return_value = fail_result

        from world.checks.types import PendingResolution

        mock_select.return_value = PendingResolution(
            check_result=fail_result,
            selected_consequence=self.gate_consequence,
        )

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        result = start_action_resolution(character, self.template, 10, context)

        assert result.current_phase == ResolutionPhase.GATE_RESOLVED
        assert len(result.gate_results) == 1
        assert result.main_result is None


class GatedPipelineContinueOnFailTests(TestCase):
    """Test GATED pipeline where gate fails with failure_aborts=False."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.success_outcome = CheckOutcomeFactory(name="Success", success_level=1)
        cls.main_pool = ConsequencePoolFactory(name="Main Continue Pool")
        cls.main_consequence = ConsequenceFactory(
            outcome_tier=cls.success_outcome, label="Main Continue", weight=10
        )
        ConsequencePoolEntryFactory(pool=cls.main_pool, consequence=cls.main_consequence)

        cls.gate_pool = ConsequencePoolFactory(name="Gate Continue Pool")
        cls.gate_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome, label="Gate Fail Continue", weight=10
        )
        ConsequencePoolEntryFactory(pool=cls.gate_pool, consequence=cls.gate_consequence)

        cls.template = ActionTemplateFactory(
            name="Resilient Spell",
            pipeline=Pipeline.GATED,
            consequence_pool=cls.main_pool,
        )
        cls.gate = ActionTemplateGateFactory(
            action_template=cls.template,
            consequence_pool=cls.gate_pool,
            failure_aborts=False,
            step_order=0,
        )

    @patch("actions.services.apply_resolution", return_value=[])
    @patch("actions.services.select_consequence_from_result")
    @patch("actions.services.perform_check")
    def test_gate_fails_continues_to_main(
        self,
        mock_check: MagicMock,
        mock_select: MagicMock,
        mock_apply: MagicMock,
    ) -> None:
        fail_result = _make_failing_check_result()
        mock_check.return_value = fail_result

        from world.checks.types import PendingResolution

        mock_select.return_value = PendingResolution(
            check_result=fail_result,
            selected_consequence=self.gate_consequence,
        )

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        result = start_action_resolution(character, self.template, 10, context)

        assert result.current_phase == ResolutionPhase.COMPLETE
        assert len(result.gate_results) == 1
        assert result.main_result is not None


class CharacterLossPauseTests(TestCase):
    """Test that gates with character_loss in pool pause for confirmation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome = CheckOutcomeFactory(name="Death", success_level=-1)
        cls.main_pool = ConsequencePoolFactory(name="Main Loss Pool")
        cls.main_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome, label="Main Normal", weight=10
        )
        ConsequencePoolEntryFactory(pool=cls.main_pool, consequence=cls.main_consequence)

        cls.gate_pool = ConsequencePoolFactory(name="Dangerous Gate Pool")
        cls.loss_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome,
            label="Character Death",
            weight=1,
            character_loss=True,
        )
        ConsequencePoolEntryFactory(pool=cls.gate_pool, consequence=cls.loss_consequence)

        cls.template = ActionTemplateFactory(
            name="Dangerous Spell",
            pipeline=Pipeline.GATED,
            consequence_pool=cls.main_pool,
        )
        cls.gate = ActionTemplateGateFactory(
            action_template=cls.template,
            consequence_pool=cls.gate_pool,
            failure_aborts=True,
            step_order=0,
        )

    def test_character_loss_pauses_pipeline(self) -> None:
        """No mocks needed — _pool_has_character_loss checks DB only."""
        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        result = start_action_resolution(character, self.template, 10, context)

        assert result.awaiting_confirmation is True
        assert result.current_phase == ResolutionPhase.GATE_PENDING
        assert result.gate_results == []
        assert result.main_result is None


class AdvanceResolutionTests(TestCase):
    """Test advance_resolution with various player decisions."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome = CheckOutcomeFactory(name="Success", success_level=1)
        cls.main_pool = ConsequencePoolFactory(name="Advance Main Pool")
        cls.main_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome, label="Advance Main", weight=10
        )
        ConsequencePoolEntryFactory(pool=cls.main_pool, consequence=cls.main_consequence)

        cls.gate_pool = ConsequencePoolFactory(name="Advance Gate Pool")
        cls.loss_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome,
            label="Advance Death",
            weight=1,
            character_loss=True,
        )
        ConsequencePoolEntryFactory(pool=cls.gate_pool, consequence=cls.loss_consequence)

        cls.template = ActionTemplateFactory(
            name="Advance Spell",
            pipeline=Pipeline.GATED,
            consequence_pool=cls.main_pool,
        )
        cls.gate = ActionTemplateGateFactory(
            action_template=cls.template,
            consequence_pool=cls.gate_pool,
            failure_aborts=True,
            step_order=0,
        )

    @patch("actions.services.apply_resolution", return_value=[])
    @patch("actions.services.select_consequence_from_result")
    @patch("actions.services.perform_check")
    def test_confirm_continues_pipeline(
        self,
        mock_check: MagicMock,
        mock_select: MagicMock,
        mock_apply: MagicMock,
    ) -> None:
        success_result = _make_check_result()
        mock_check.return_value = success_result

        from world.checks.types import PendingResolution

        mock_select.return_value = PendingResolution(
            check_result=success_result,
            selected_consequence=self.loss_consequence,
        )

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None
        context.character = character

        # First start — should pause
        pending = start_action_resolution(character, self.template, 10, context)
        assert pending.awaiting_confirmation is True

        # Then advance with confirm
        result = advance_resolution(pending, context, player_decision=PlayerDecision.CONFIRM)

        assert result.awaiting_confirmation is False
        assert result.current_phase == ResolutionPhase.COMPLETE
        assert result.main_result is not None

    def test_abort_completes_without_resolution(self) -> None:
        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        pending = start_action_resolution(character, self.template, 10, context)
        assert pending.awaiting_confirmation is True

        result = advance_resolution(pending, context, player_decision=PlayerDecision.ABORT)

        assert result.current_phase == ResolutionPhase.COMPLETE
        assert result.awaiting_confirmation is False
        assert result.main_result is None
        assert result.gate_results == []


class EmptyPoolTests(TestCase):
    """Test that an empty pool produces a no-op step result."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.empty_pool = ConsequencePoolFactory(name="Empty Pipeline Pool")
        cls.template = ActionTemplateFactory(
            name="Empty Pool Template",
            pipeline=Pipeline.SINGLE,
            consequence_pool=cls.empty_pool,
        )

    @patch("actions.services.perform_check")
    def test_empty_pool_no_consequence(
        self,
        mock_check: MagicMock,
    ) -> None:
        check_result = _make_check_result()
        mock_check.return_value = check_result

        character = MagicMock()
        character.pk = 1
        context = MagicMock(spec=ResolutionContext)
        context.challenge_instance = None

        result = start_action_resolution(character, self.template, 10, context)

        assert result.current_phase == ResolutionPhase.COMPLETE
        assert result.main_result is not None
        assert result.main_result.consequence_id is None


class TestRunMainStepNullPool(TestCase):
    """_run_main_step handles ActionTemplate with no consequence pool."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.checks.factories import CheckCategoryFactory, CheckTypeFactory

        category = CheckCategoryFactory(name="NullPoolCat")
        cls.check_type = CheckTypeFactory(name="NullPoolCheck", category=category)

    @patch("actions.services.perform_check")
    def test_null_pool_returns_check_only_result(self, mock_check: MagicMock) -> None:
        """When consequence_pool is None, still returns a StepResult with check_result."""
        from actions.models.action_templates import ActionTemplate
        from actions.services import _run_main_step
        from world.checks.types import ResolutionContext

        mock_result = MagicMock()
        mock_result.outcome_name = "Success"
        mock_result.success_level = 1
        mock_check.return_value = mock_result

        template = ActionTemplate.objects.create(
            name="Test Null Pool Action",
            check_type=self.check_type,
            consequence_pool=None,
            category="test",
        )
        character = MagicMock()
        context = MagicMock(spec=ResolutionContext)

        result = _run_main_step(character, template, 45, context)

        assert result.check_result == mock_result
        assert result.applied_effect_ids is None
        mock_check.assert_called_once()

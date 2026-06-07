"""Tests for use_technique orchestrator."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import ReactiveConditionFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.services.techniques import get_runtime_technique_stats
from world.magic.types import TechniqueUseResult
from world.mechanics.factories import CharacterEngagementFactory
from world.traits.factories import CheckOutcomeFactory


class DerivePowerTests(TestCase):
    """Test the _derive_power helper."""

    def test_derive_power_equals_channeled_intensity_in_pr1(self) -> None:
        from world.magic.services.techniques import _derive_power

        self.assertEqual(
            _derive_power(channeled_intensity=7, technique=None, character=None).total, 7
        )


# ---------------------------------------------------------------------------
# Pre-cast MODIFY_PAYLOAD power read-back
# ---------------------------------------------------------------------------

SELF_FILTER = {"path": "caster", "op": "==", "value": "self"}


def _create_room(key: str = "PowerTestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_multiply_power_flow(factor: float) -> object:
    """Return a FlowDefinition with a MODIFY_PAYLOAD step that multiplies power."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.MODIFY_PAYLOAD,
        parameters={"field": "power", "op": "multiply", "value": factor},
    )
    return flow


class PreCastPowerReadBackTests(TestCase):
    """A pre-cast MODIFY_PAYLOAD on power is read back into resolve_fn and CAST/AFFECTED."""

    @classmethod
    def setUpTestData(cls) -> None:
        # intensity=10 so 10 * 0.5 = 5.0 — avoids fractional truncation ambiguity
        cls.technique = TechniqueFactory(intensity=10, control=15, anima_cost=3)

    def setUp(self) -> None:
        self.room = _create_room("PreCastPowerRoom")
        self.anima = CharacterAnimaFactory(current=20, maximum=20)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)
        self.character.location = self.room

    def test_resolve_fn_receives_halved_power(self) -> None:
        """Pre-cast trigger multiplies power by 0.5; resolver receives halved value."""
        half_flow = _make_multiply_power_flow(0.5)
        ReactiveConditionFactory(
            event_name=EventName.TECHNIQUE_PRE_CAST,
            filter_condition=SELF_FILTER,
            flow_definition=half_flow,
            target=self.character,
        )
        self.character.trigger_handler._populated = False

        expected_runtime_intensity = get_runtime_technique_stats(
            self.technique, self.character
        ).intensity
        # MODIFY_PAYLOAD multiply does not truncate to int; use numeric equality
        expected_power = expected_runtime_intensity * 0.5

        captured: dict[str, object] = {}

        def spy(*, power: int, ledger: object = None) -> SimpleNamespace:
            captured["power"] = power
            return SimpleNamespace(check_result=None)

        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=spy,
        )

        self.assertIn("power", captured)
        self.assertEqual(captured["power"], expected_power)

    def test_resolve_fn_receives_power_kwarg(self) -> None:
        """resolve_fn must be called with power as a keyword argument."""
        captured: dict[str, object] = {}

        def spy(*, power: int, ledger: object = None) -> SimpleNamespace:
            captured["power"] = power
            return SimpleNamespace(check_result=None)

        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=spy,
        )

        self.assertIn("power", captured)


class PreCastModifyPowerInvariantTests(TestCase):
    """A pre-cast MODIFY_PAYLOAD on power must NOT affect caster-side outputs.

    power is a downstream scaling hint for the resolve_fn; the cost/mishap/soulfray
    path runs on channeled_intensity, which is fixed before the PRE_CAST hook fires.
    These tests prove the invariant by running use_technique with and without a
    ward that halves power and asserting that caster-side outputs are identical.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(
            intensity=5,
            control=10,
            anima_cost=3,
        )

    def _run_with_ward(self, *, with_ward: bool) -> "tuple[int, object, object]":
        """Return (anima_delta, was_mishap, soulfray_result) for one use_technique call."""
        room = _create_room(f"InvariantRoom{'Ward' if with_ward else 'Control'}")
        anima = CharacterAnimaFactory(current=20, maximum=20)
        character = anima.character
        CharacterEngagementFactory(character=character)
        character.location = room

        if with_ward:
            half_flow = _make_multiply_power_flow(0.5)
            ReactiveConditionFactory(
                event_name=EventName.TECHNIQUE_PRE_CAST,
                filter_condition=SELF_FILTER,
                flow_definition=half_flow,
                target=character,
            )
            character.trigger_handler._populated = False

        def spy(*, power: int, ledger: object = None) -> SimpleNamespace:
            return SimpleNamespace(check_result=None)

        result = use_technique(
            character=character,
            technique=self.technique,
            resolve_fn=spy,
        )

        anima.refresh_from_db()
        anima_delta = 20 - anima.current
        soulfray_severity = (
            result.soulfray_result.severity_added if result.soulfray_result is not None else None
        )
        return anima_delta, result.was_mishap, soulfray_severity

    def test_power_ward_does_not_change_anima_cost(self) -> None:
        """Pre-cast power *= 0.5 must not change the anima deducted."""
        delta_control, _, _ = self._run_with_ward(with_ward=False)
        delta_ward, _, _ = self._run_with_ward(with_ward=True)
        self.assertEqual(
            delta_control,
            delta_ward,
            "Anima delta must be identical with and without a pre-cast power modifier.",
        )

    def test_power_ward_does_not_change_mishap_flag(self) -> None:
        """Pre-cast power *= 0.5 must not change was_mishap."""
        _, mishap_control, _ = self._run_with_ward(with_ward=False)
        _, mishap_ward, _ = self._run_with_ward(with_ward=True)
        self.assertEqual(
            mishap_control,
            mishap_ward,
            "was_mishap must be identical with and without a pre-cast power modifier.",
        )

    def test_power_ward_does_not_change_soulfray_severity(self) -> None:
        """Pre-cast power *= 0.5 must not change soulfray severity (both None here)."""
        _, _, soulfray_control = self._run_with_ward(with_ward=False)
        _, _, soulfray_ward = self._run_with_ward(with_ward=True)
        self.assertEqual(
            soulfray_control,
            soulfray_ward,
            "Soulfray severity must be identical with and without a pre-cast power modifier.",
        )


class UseTechniqueBasicTests(TestCase):
    """Test the orchestrator with sufficient anima and controlled technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(
            intensity=5,
            control=10,
            anima_cost=8,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=10, maximum=10)
        self.character = self.anima.character
        # Engage the character so social safety bonus doesn't apply
        CharacterEngagementFactory(character=self.character)

    def test_sufficient_anima_no_checkpoint(self) -> None:
        """Technique with enough anima resolves without confirmation."""
        mock_resolve = MagicMock(return_value="resolution_result")

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=mock_resolve,
        )

        assert isinstance(result, TechniqueUseResult)
        assert result.confirmed is True
        assert result.resolution_result == "resolution_result"
        assert result.mishap is None
        mock_resolve.assert_called_once()

        # Anima deducted: cost=8, control_delta=5, effective=3
        self.anima.refresh_from_db()
        assert self.anima.current == 7  # 10 - 3

    def test_control_exceeds_intensity_no_mishap(self) -> None:
        """When control > intensity, no mishap rider fires."""
        mock_resolve = MagicMock(return_value="ok")

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=mock_resolve,
        )

        assert result.mishap is None


class UseTechniqueSoulfrayCheckpointTests(TestCase):
    """Test the orchestrator's soulfray warning checkpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        # High intensity, low control = expensive
        cls.technique = TechniqueFactory(
            intensity=20,
            control=5,
            anima_cost=10,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=5, maximum=10)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)

    @patch("world.magic.services.techniques.get_soulfray_warning")
    def test_soulfray_warning_pauses_for_confirmation(
        self,
        mock_warning: MagicMock,
    ) -> None:
        """Soulfray warning pauses for confirmation with stage info."""
        from world.magic.types import SoulfrayWarning

        mock_warning.return_value = SoulfrayWarning(
            stage_name="Flickering",
            stage_description="Anima flickers.",
            has_death_risk=False,
        )

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(),
            confirm_soulfray_risk=False,  # Player declines
        )

        assert result.confirmed is False
        assert result.resolution_result is None
        assert result.soulfray_warning is not None
        assert result.soulfray_warning.stage_name == "Flickering"

        # Anima NOT deducted when cancelled
        self.anima.refresh_from_db()
        assert self.anima.current == 5

    def test_no_soulfray_warning_proceeds_normally(self) -> None:
        """Without soulfray warning, confirm_soulfray_risk=False has no effect."""
        mock_resolve = MagicMock(return_value="resolved")

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=mock_resolve,
            confirm_soulfray_risk=False,  # No warning exists, so proceeds
        )

        assert result.confirmed is True
        assert result.resolution_result == "resolved"
        mock_resolve.assert_called_once()

    def test_overburn_confirmed_deducts_and_resolves(self) -> None:
        """Confirmed overburn deducts anima, resolves, applies soulfray."""
        mock_resolve = MagicMock(return_value="resolved")

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=mock_resolve,
            confirm_soulfray_risk=True,
        )

        assert result.confirmed is True
        assert result.resolution_result == "resolved"
        assert result.anima_cost.deficit > 0
        mock_resolve.assert_called_once()

        # Anima fully drained
        self.anima.refresh_from_db()
        assert self.anima.current == 0


class UseTechniqueMishapTests(TestCase):
    """Test mishap rider when intensity > control."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Intensity > control but enough anima
        cls.technique = TechniqueFactory(
            intensity=15,
            control=5,
            anima_cost=5,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=20, maximum=20)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)

    @patch("world.magic.services.techniques.select_mishap_pool")
    def test_mishap_fires_when_intensity_exceeds_control(
        self,
        mock_pool: MagicMock,
    ) -> None:
        """Mishap rider fires after resolution when intensity > control."""
        mock_pool.return_value = None  # No pool configured yet

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="resolved"),
        )

        # select_mishap_pool called with control_deficit=10
        mock_pool.assert_called_once_with(10)
        assert result.resolution_result == "resolved"


class UseTechniqueCheckResultExtractionTests(TestCase):
    """Test that use_technique extracts check_result from PendingActionResolution."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_type = CheckTypeFactory()
        cls.failure_outcome = CheckOutcomeFactory()
        # Intensity > control to trigger mishap path
        cls.technique = TechniqueFactory(
            intensity=10,
            control=1,
            anima_cost=5,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=20, maximum=20)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)

    @patch("world.magic.services.techniques.select_mishap_pool")
    def test_use_technique_extracts_check_result_from_pending_resolution(
        self,
        mock_pool: MagicMock,
    ) -> None:
        """When resolve_fn returns PendingActionResolution, mishap uses its check_result."""
        from actions.types import PendingActionResolution, StepResult
        from world.checks.types import CheckResult

        mock_check_result = CheckResult(
            check_type=self.check_type,
            outcome=self.failure_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        mock_resolution = PendingActionResolution(
            template_id=1,
            character_id=self.character.pk,
            target_difficulty=45,
            resolution_context_data={},
            current_phase="COMPLETE",
            main_result=StepResult(
                step_label="main",
                check_result=mock_check_result,
                consequence_id=None,
            ),
        )

        mock_pool.return_value = None  # No pool configured, so mishap stays None

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda *, power, ledger: mock_resolution,  # noqa: ARG005
            confirm_soulfray_risk=True,
        )

        # Resolution result is the PendingActionResolution
        assert result.resolution_result is mock_resolution
        # select_mishap_pool was called (control_deficit = 10 - 1 = 9)
        mock_pool.assert_called_once_with(9)

    @patch("world.magic.services.techniques._resolve_mishap")
    @patch("world.magic.services.techniques.select_mishap_pool")
    def test_extracted_check_result_passed_to_resolve_mishap(
        self,
        mock_pool: MagicMock,
        mock_resolve_mishap: MagicMock,
    ) -> None:
        """Extracted check_result from PendingActionResolution is passed to _resolve_mishap."""
        from actions.types import PendingActionResolution, StepResult
        from world.checks.types import CheckResult

        mock_check_result = CheckResult(
            check_type=self.check_type,
            outcome=self.failure_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        mock_resolution = PendingActionResolution(
            template_id=1,
            character_id=self.character.pk,
            target_difficulty=45,
            resolution_context_data={},
            current_phase="COMPLETE",
            main_result=StepResult(
                step_label="main",
                check_result=mock_check_result,
                consequence_id=None,
            ),
        )

        fake_pool = MagicMock()
        mock_pool.return_value = fake_pool
        mock_resolve_mishap.return_value = MagicMock()

        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda *, power, ledger: mock_resolution,  # noqa: ARG005
            confirm_soulfray_risk=True,
        )

        # _resolve_mishap must have been called with the extracted check_result
        mock_resolve_mishap.assert_called_once_with(self.character, fake_pool, mock_check_result)

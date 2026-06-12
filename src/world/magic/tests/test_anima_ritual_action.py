"""Tests for the anima_ritual action resolver.

Tests verify:
- The resolver fires apply_anima_ritual_outcome when an anima_ritual action is accepted.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    CharacterAnimaFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
)
from world.magic.models.anima import AnimaRitualPerformance
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_resolvers import _RESOLVER_REGISTRY
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.traits.factories import CheckOutcomeFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PERFORM_CHECK_PATCH = "world.scenes.action_services.start_action_resolution"
_AWARD_KUDOS_PATCH = "world.scenes.action_services.award_kudos"


def _make_pending_resolution(outcome_row: object) -> PendingActionResolution:
    """Build a PendingActionResolution wrapping a real CheckOutcome row."""
    check_type = CheckTypeFactory()
    check_result = CheckResult(
        check_type=check_type,
        outcome=outcome_row,  # type: ignore[arg-type]
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=15,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


def _make_scene_action_ritual():
    """Create a SCENE_ACTION Ritual + RitualCheckConfig."""
    ritual = RitualFactory(
        execution_kind=RitualExecutionKind.SCENE_ACTION,
        service_function_path="",
        flow=None,
    )
    RitualCheckConfigFactory(ritual=ritual)
    return ritual


class AnimaRitualResolverTests(TestCase):
    """The anima_ritual resolver is registered and applies outcome on accept."""

    def setUp(self) -> None:
        # Ensure the resolver module is imported (apps.ready() fires this in real server;
        # Django test runner does call ready(), so this is a belt-and-suspenders guard).
        from world.magic.services import anima_ritual_action  # noqa: F401

        self.award_kudos_patcher = patch(_AWARD_KUDOS_PATCH)
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def _setup_ritual_scene(self, success_level: int = 1) -> tuple:
        """Create a full ritual+scene setup and a real CheckOutcome row.

        The ritual is attached to the action request via snapshot_ritual so the
        resolver can read it without needing author_account on the character.
        """
        persona = PersonaFactory()
        sheet = persona.character_sheet
        target_persona = PersonaFactory()

        ritual = _make_scene_action_ritual()
        anima = CharacterAnimaFactory(
            character=sheet.character,
            current=2,
            maximum=10,
        )
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=1,
        )
        scene = SceneFactory(is_active=True)
        outcome = CheckOutcomeFactory(
            name=f"TestOutcome_sl{success_level}_{id(object())}",
            success_level=success_level,
        )
        action_template = ActionTemplateFactory()

        action_request = SceneActionRequestFactory(
            scene=scene,
            initiator_persona=persona,
            target_persona=target_persona,
            action_key="anima_ritual",
            status=ActionRequestStatus.PENDING,
        )
        # Set snapshot_ritual so the resolver reads the correct Ritual row.
        action_request.action_template = action_template
        action_request.snapshot_ritual = ritual
        action_request.save(update_fields=["action_template", "snapshot_ritual"])

        return action_request, ritual, anima, outcome

    def test_resolver_is_registered(self) -> None:
        """The 'anima_ritual' action_key is registered in the resolver registry."""
        self.assertIn("anima_ritual", _RESOLVER_REGISTRY)

    def test_accept_recovers_anima(self) -> None:
        """Accepting an anima_ritual request recovers anima via the resolver."""
        action_request, _ritual, anima, outcome = self._setup_ritual_scene(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        anima.refresh_from_db()
        # success budget=6, no soulfray, anima goes from 2 to 8
        self.assertEqual(anima.current, 8)

    def test_accept_creates_performance_row(self) -> None:
        """Accepting creates an AnimaRitualPerformance audit row."""
        action_request, ritual, _anima, outcome = self._setup_ritual_scene(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertTrue(AnimaRitualPerformance.objects.filter(ritual=ritual).exists())

    def test_deny_does_not_recover(self) -> None:
        """Denying an anima_ritual request does not call the resolver."""
        action_request, ritual, anima, _outcome = self._setup_ritual_scene(success_level=1)

        respond_to_action_request(action_request=action_request, decision=ConsentDecision.DENY)

        anima.refresh_from_db()
        self.assertEqual(anima.current, 2)  # unchanged
        self.assertFalse(AnimaRitualPerformance.objects.filter(ritual=ritual).exists())

    def test_crit_success_fills_anima_to_max(self) -> None:
        """Crit outcome fills anima to max regardless of budget."""
        action_request, _ritual, anima, outcome = self._setup_ritual_scene(success_level=2)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        anima.refresh_from_db()
        self.assertEqual(anima.current, 10)  # maximum

    def test_no_ritual_configured_resolver_no_ops(self) -> None:
        """When the request has no snapshot_ritual and initiator has no authored ritual,
        the resolver exits silently."""
        persona = PersonaFactory()
        target_persona = PersonaFactory()
        # No ritual created, no snapshot_ritual on request
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        SoulfrayConfigFactory()
        scene = SceneFactory(is_active=True)
        outcome = CheckOutcomeFactory(name="NoRitualOutcome", success_level=1)
        action_template = ActionTemplateFactory()

        action_request = SceneActionRequestFactory(
            scene=scene,
            initiator_persona=persona,
            target_persona=target_persona,
            action_key="anima_ritual",
            status=ActionRequestStatus.PENDING,
        )
        action_request.action_template = action_template
        action_request.save(update_fields=["action_template"])

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            # Should not raise
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertIsNotNone(result)
        self.assertFalse(AnimaRitualPerformance.objects.exists())

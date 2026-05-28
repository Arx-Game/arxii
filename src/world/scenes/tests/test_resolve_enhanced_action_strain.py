"""Tests that strain plumbs from SceneActionRequest into Interaction at resolution."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory


def _make_pending_resolution(success: bool = True) -> PendingActionResolution:
    """Build a minimal PendingActionResolution for mocking."""
    check_result = MagicMock()
    check_result.success_level = 1 if success else -1
    check_result.outcome_name = "Success" if success else "Failure"
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


class ResolveEnhancedActionStrainTests(TestCase):
    """The Interaction created at non-clash resolution records strain_committed."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

    def setUp(self) -> None:
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    @patch("world.scenes.action_services.start_action_resolution")
    def test_resolved_interaction_records_strain(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
            strain_commitment=5,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(request.result_interaction)
        self.assertEqual(request.result_interaction.strain_committed, 5)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_zero_strain_persisted_as_zero(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
            strain_commitment=0,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        request.refresh_from_db()
        self.assertIsNotNone(request.result_interaction)
        self.assertEqual(request.result_interaction.strain_committed, 0)

"""Tests for scene action services: create_action_request and respond_to_action_request."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_resolvers import _RESOLVER_REGISTRY, register_resolver
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.scenes.place_models import InteractionReceiver
from world.scenes.types import EnhancedSceneActionResult


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


class TestCreateActionRequest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

    def test_creates_pending_request(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        assert request.pk is not None
        assert request.status == ActionRequestStatus.PENDING
        assert request.action_key == "intimidate"
        assert request.difficulty_choice == DifficultyChoice.NORMAL

    def test_creates_with_custom_difficulty(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="persuade",
            difficulty_choice=DifficultyChoice.HARD,
        )
        assert request.difficulty_choice == DifficultyChoice.HARD


class TestRespondToActionRequest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

    def test_deny_sets_status(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.DENY,
        )
        assert result is None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.DENIED
        assert request.resolved_at is not None

    @patch("world.scenes.action_services.start_action_resolution")
    def test_accept_resolves_and_creates_interaction(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)

        action_template = ActionTemplateFactory()
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        request.action_template = action_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )
        assert result is not None
        assert isinstance(result, EnhancedSceneActionResult)
        assert result.action_key == "intimidate"
        assert result.action_resolution is not None

        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        assert request.resolved_at is not None
        assert request.result_interaction is not None

        # Result interaction should have the target as receiver
        receivers = InteractionReceiver.objects.filter(interaction=request.result_interaction)
        assert receivers.count() == 1
        assert receivers.first().persona == self.target

    def test_respond_to_non_pending_returns_none(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        request.status = ActionRequestStatus.RESOLVED
        request.save(update_fields=["status"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )
        assert result is None

    @patch("world.scenes.action_services.start_action_resolution")
    def test_accept_with_hard_difficulty(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)

        action_template = ActionTemplateFactory()
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="persuade",
            difficulty_choice=DifficultyChoice.HARD,
        )
        request.action_template = action_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )
        assert result is not None
        request.refresh_from_db()
        assert request.resolved_difficulty == DIFFICULTY_VALUES[DifficultyChoice.HARD]

    def test_accept_without_template_raises(self) -> None:
        """No action_template raises ValueError (not silent failure)."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        # action_template is None by default

        with self.assertRaises(ValueError):
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )


class TestResolverIntegration(TestCase):
    """Tests that the action_resolvers registry is invoked by respond_to_action_request."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

    @patch("world.scenes.action_services.start_action_resolution")
    def test_resolver_called_on_accept(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)

        captured: list[tuple[int, object]] = []

        def fake_resolver(request, outcome):
            captured.append((request.pk, outcome))

        register_resolver("test_action", fake_resolver)
        self.addCleanup(lambda: _RESOLVER_REGISTRY.pop("test_action", None))

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="test_action",
        )
        action_request.action_template = self.action_template
        action_request.save(update_fields=["action_template"])

        respond_to_action_request(action_request=action_request, decision=ConsentDecision.ACCEPT)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], action_request.pk)

    def test_resolver_not_called_on_deny(self) -> None:
        captured: list[int] = []

        def _deny_resolver(_request, _outcome):
            captured.append(1)

        register_resolver("test_action_deny", _deny_resolver)
        self.addCleanup(lambda: _RESOLVER_REGISTRY.pop("test_action_deny", None))

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="test_action_deny",
        )
        respond_to_action_request(action_request=action_request, decision=ConsentDecision.DENY)
        self.assertEqual(captured, [])

    @patch("world.scenes.action_services.start_action_resolution")
    def test_no_resolver_registered_no_op(self, mock_resolve: MagicMock) -> None:
        """Accepting with no resolver registered should not raise."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="unknown_action_xyz",
        )
        action_request.action_template = self.action_template
        action_request.save(update_fields=["action_template"])

        # Should not raise
        result = respond_to_action_request(
            action_request=action_request, decision=ConsentDecision.ACCEPT
        )
        self.assertIsNotNone(result)

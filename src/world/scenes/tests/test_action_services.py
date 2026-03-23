"""Tests for scene action services: create_action_request and respond_to_action_request."""

from django.test import TestCase

from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.place_models import InteractionReceiver


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

    def test_accept_resolves_and_creates_interaction(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )
        assert result is not None
        assert result.success is True
        assert result.action_key == "intimidate"

        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        assert request.resolved_at is not None
        assert request.resolved_difficulty == DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
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

    def test_accept_with_hard_difficulty(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="persuade",
            difficulty_choice=DifficultyChoice.HARD,
        )
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )
        assert result is not None
        request.refresh_from_db()
        assert request.resolved_difficulty == DIFFICULTY_VALUES[DifficultyChoice.HARD]

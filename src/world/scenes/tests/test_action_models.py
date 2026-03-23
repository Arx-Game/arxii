"""Tests for SceneActionRequest model."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.scenes.action_constants import ActionRequestStatus, DifficultyChoice
from world.scenes.factories import (
    PersonaFactory,
    SceneActionRequestFactory,
    SceneFactory,
)


class TestSceneActionRequest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

    def test_create_with_action_key(self) -> None:
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        assert request.pk is not None
        assert request.action_key == "intimidate"
        assert request.status == ActionRequestStatus.PENDING
        assert request.difficulty_choice == DifficultyChoice.NORMAL
        assert request.action_template is None

    def test_clean_requires_action_key_or_template(self) -> None:
        request = SceneActionRequestFactory.build(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="",
            action_template=None,
        )
        with self.assertRaises(ValidationError):
            request.clean()

    def test_clean_passes_with_action_key(self) -> None:
        request = SceneActionRequestFactory.build(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="persuade",
        )
        request.clean()  # Should not raise

    def test_str(self) -> None:
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        result = str(request)
        assert self.initiator.name in result
        assert self.target.name in result
        assert "intimidate" in result

    def test_status_transitions(self) -> None:
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
        )
        assert request.status == ActionRequestStatus.PENDING

        request.status = ActionRequestStatus.ACCEPTED
        request.save(update_fields=["status"])
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.ACCEPTED

    def test_resolved_difficulty(self) -> None:
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            difficulty_choice=DifficultyChoice.HARD,
            resolved_difficulty=60,
        )
        assert request.resolved_difficulty == 60
        assert request.difficulty_choice == DifficultyChoice.HARD

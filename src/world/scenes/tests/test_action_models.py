"""Tests for SceneActionRequest model."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.magic.constants import RitualExecutionKind
from world.magic.factories import RitualFactory, RitualSceneActionConfigFactory
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

    def test_snapshot_fields_default_null(self) -> None:
        """Snapshot fields should default to NULL."""
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
        )
        self.assertIsNone(request.snapshot_ritual)
        self.assertIsNone(request.snapshot_stat)
        self.assertIsNone(request.snapshot_skill)
        self.assertIsNone(request.snapshot_specialization)
        self.assertIsNone(request.snapshot_resonance)
        self.assertIsNone(request.snapshot_check_type)
        self.assertIsNone(request.snapshot_target_difficulty)

    def test_snapshot_fields_can_be_set(self) -> None:
        """Snapshot fields can be set from a ritual config."""
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        config = RitualSceneActionConfigFactory(ritual=ritual)
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            snapshot_ritual=ritual,
            snapshot_stat=config.stat,
            snapshot_skill=config.skill,
            snapshot_specialization=config.specialization,
            snapshot_resonance=config.resonance,
            snapshot_check_type=config.check_type,
            snapshot_target_difficulty=config.target_difficulty,
        )
        self.assertEqual(request.snapshot_ritual, ritual)
        self.assertEqual(request.snapshot_stat, config.stat)
        self.assertEqual(request.snapshot_skill, config.skill)
        self.assertEqual(request.snapshot_specialization, config.specialization)
        self.assertEqual(request.snapshot_resonance, config.resonance)
        self.assertEqual(request.snapshot_check_type, config.check_type)
        self.assertEqual(request.snapshot_target_difficulty, config.target_difficulty)

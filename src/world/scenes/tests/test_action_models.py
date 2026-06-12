"""Tests for SceneActionRequest model."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import RitualExecutionKind, TargetKind
from world.magic.factories import (
    ResonanceFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    TechniqueFactory,
    ThreadFactory,
)
from world.scenes.action_constants import ActionRequestStatus, CastPullTier, DifficultyChoice
from world.scenes.action_models import SceneActionRequest, SceneCastPullDeclaration
from world.scenes.factories import (
    PersonaFactory,
    SceneActionRequestFactory,
    SceneFactory,
)
from world.scenes.models import Interaction


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
        config = RitualCheckConfigFactory(ritual=ritual)
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


class SceneActionRequestStrainFieldTests(TestCase):
    def test_strain_commitment_field_exists(self) -> None:
        field = SceneActionRequest._meta.get_field("strain_commitment")
        self.assertEqual(field.default, 0)


class InteractionStrainCommittedTests(TestCase):
    def test_strain_committed_field_exists(self) -> None:
        field = Interaction._meta.get_field("strain_committed")
        self.assertEqual(field.default, 0)


class StandalonecastTests(TestCase):
    """Tests for standalone technique cast support on SceneActionRequest."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.technique = TechniqueFactory(damage_profile=False)

    def test_standalone_cast_passes_full_clean(self) -> None:
        """A request with technique set and no target/action_key/template passes validation."""
        request = SceneActionRequest(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=None,
            technique=self.technique,
            action_key="",
        )
        request.full_clean()  # must not raise

    def test_standalone_cast_is_standalone_cast_true(self) -> None:
        """is_standalone_cast is True when only technique is set."""
        request = SceneActionRequest(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=None,
            technique=self.technique,
            action_key="",
        )
        assert request.is_standalone_cast is True

    def test_no_technique_no_action_raises_validation_error(self) -> None:
        """A request with no technique, no action_key, and no template raises ValidationError."""
        request = SceneActionRequest(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=None,
            action_key="",
            action_template=None,
            technique=None,
        )
        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_action_key_plus_technique_is_not_standalone(self) -> None:
        """is_standalone_cast is False when action_key is also set."""
        request = SceneActionRequest(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=None,
            action_key="intimidate",
            technique=self.technique,
        )
        assert request.is_standalone_cast is False


class SceneCastPullDeclarationTests(TestCase):
    """Persistence and related-name access for SceneCastPullDeclaration."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.technique = TechniqueFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=cls.technique,
        )
        cls.request = SceneActionRequest.objects.create(
            scene=SceneFactory(),
            initiator_persona=cls.sheet.primary_persona,
            technique=cls.technique,
            status=ActionRequestStatus.PENDING,
        )

    def test_declaration_round_trip(self) -> None:
        decl = SceneCastPullDeclaration.objects.create(
            request=self.request,
            resonance=self.resonance,
            tier=CastPullTier.TIER_2,
        )
        decl.threads.set([self.thread])
        self.assertEqual(self.request.pull_declaration.tier, CastPullTier.TIER_2)
        self.assertEqual(
            list(self.request.pull_declaration.threads.values_list("pk", flat=True)),
            [self.thread.pk],
        )

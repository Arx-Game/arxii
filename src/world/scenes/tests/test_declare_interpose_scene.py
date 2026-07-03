from django.test import TestCase

from world.scenes.constants import RoundStatus, SceneRoundMode, SceneRoundParticipantStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.models import SceneActionDeclaration
from world.scenes.round_services import _resolve_scene_declarations, declare_interpose_scene


class DeclareInterposeSceneTests(TestCase):
    def test_declares_interpose_target(self):
        scene_round = SceneRoundFactory(status=RoundStatus.DECLARING, mode=SceneRoundMode.STRICT)
        participant = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        ally = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )

        decl = declare_interpose_scene(participant, ally)

        self.assertEqual(decl.interpose_target_id, ally.pk)
        self.assertIsNone(decl.challenge_instance)
        self.assertFalse(decl.is_pass)

    def test_cannot_interpose_self(self):
        scene_round = SceneRoundFactory(status=RoundStatus.DECLARING, mode=SceneRoundMode.STRICT)
        participant = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        with self.assertRaisesMessage(ValueError, "yourself"):
            declare_interpose_scene(participant, participant)

    def test_survives_resolve_scene_declarations(self):
        scene_round = SceneRoundFactory(status=RoundStatus.DECLARING, mode=SceneRoundMode.STRICT)
        participant = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        ally = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        declare_interpose_scene(participant, ally)

        _resolve_scene_declarations(scene_round)

        self.assertTrue(
            SceneActionDeclaration.objects.filter(
                scene_round=scene_round, interpose_target=ally
            ).exists()
        )

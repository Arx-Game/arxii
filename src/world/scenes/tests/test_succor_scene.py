from django.test import TestCase

from world.scenes.constants import RoundStatus, SceneRoundMode, SceneRoundParticipantStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.round_context import SceneRoundContext
from world.scenes.round_services import declare_succor_scene


class DeclareSuccorSceneTests(TestCase):
    def test_declare_succor_scene_writes_declaration(self):
        scene_round = SceneRoundFactory(status=RoundStatus.DECLARING, mode=SceneRoundMode.STRICT)
        succorer = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        ally = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        declaration = declare_succor_scene(succorer, ally)
        self.assertEqual(declaration.succor_target_id, ally.pk)
        self.assertIsNone(declaration.succor_resolution)


class SceneGetCoverForTests(TestCase):
    def test_no_succor_declared_returns_no_cover(self):
        scene_round = SceneRoundFactory(status=RoundStatus.RESOLVING)
        target = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        ctx = SceneRoundContext(scene_round)
        result = ctx.get_cover_for(target.character_sheet, damage_type=None)
        self.assertEqual(result, 1.0)

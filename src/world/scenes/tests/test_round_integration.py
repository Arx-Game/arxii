from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.round_services import advance_scene_round


class NonCombatRoundIntegrationTests(TestCase):
    def test_round_advance_ticks_dot_for_participants(self):
        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=2
        )
        inst = ConditionInstanceFactory(
            target=sheet.character, condition=template, rounds_remaining=2
        )
        advance_scene_round(rnd)
        inst.refresh_from_db()
        assert inst.rounds_remaining == 1

    def test_afk_safety_round_with_no_participants_ticks_nothing(self):
        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        advance_scene_round(rnd)  # must not raise with zero participants
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.BETWEEN_ROUNDS

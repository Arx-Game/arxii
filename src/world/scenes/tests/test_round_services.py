from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.round_services import advance_scene_round, end_scene_round, start_scene_round


class SceneRoundServiceTests(TestCase):
    def test_start_sets_declaring_and_increments(self):
        rnd = SceneRoundFactory(status=RoundStatus.BETWEEN_ROUNDS, round_number=0)
        start_scene_round(rnd)
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.DECLARING
        assert rnd.round_number == 1

    def test_advance_ticks_participant_conditions(self):
        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        target = sheet.character
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(target=target, condition=template, rounds_remaining=3)

        advance_scene_round(rnd)

        inst.refresh_from_db()
        assert inst.rounds_remaining == 2
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.BETWEEN_ROUNDS

    def test_end_marks_completed(self):
        rnd = SceneRoundFactory(status=RoundStatus.BETWEEN_ROUNDS)
        end_scene_round(rnd)
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.COMPLETED
        assert rnd.completed_at is not None

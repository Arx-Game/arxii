from django.db import IntegrityError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus, SceneRoundParticipantStatus
from world.scenes.models import SceneRound, SceneRoundParticipant


class RoundEnumTests(TestCase):
    def test_round_status_values(self):
        assert RoundStatus.DECLARING == "declaring"
        assert RoundStatus.RESOLVING == "resolving"
        assert RoundStatus.BETWEEN_ROUNDS == "between_rounds"
        assert RoundStatus.COMPLETED == "completed"

    def test_participant_status_values(self):
        assert SceneRoundParticipantStatus.ACTIVE == "active"
        assert SceneRoundParticipantStatus.LEFT == "left"


class SceneRoundModelTests(TestCase):
    def setUp(self):
        self.room = ObjectDB.objects.create(db_key="TestRoom")

    def test_create_scene_round_defaults(self):
        rnd = SceneRound.objects.create(room=self.room)
        assert rnd.status == RoundStatus.BETWEEN_ROUNDS
        assert rnd.round_number == 0

    def test_one_active_round_per_room(self):
        SceneRound.objects.create(room=self.room, status=RoundStatus.DECLARING)
        with self.assertRaises(IntegrityError):
            SceneRound.objects.create(room=self.room, status=RoundStatus.DECLARING)

    def test_completed_rounds_do_not_conflict(self):
        SceneRound.objects.create(room=self.room, status=RoundStatus.COMPLETED)
        SceneRound.objects.create(room=self.room, status=RoundStatus.DECLARING)

    def test_participant_unique_per_round(self):
        rnd = SceneRound.objects.create(room=self.room)
        sheet = CharacterSheetFactory()
        SceneRoundParticipant.objects.create(scene_round=rnd, character_sheet=sheet)
        with self.assertRaises(IntegrityError):
            SceneRoundParticipant.objects.create(scene_round=rnd, character_sheet=sheet)


class RoundFactorySmokeTests(TestCase):
    def test_factories_build(self):
        from world.scenes.factories import SceneRoundParticipantFactory

        p = SceneRoundParticipantFactory()
        assert p.scene_round_id is not None
        assert p.character_sheet_id is not None


class SceneActionDeclarationTests(TestCase):
    def test_scene_action_declaration_unique_per_participant_per_round(self):
        from django.db import IntegrityError

        from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
        from world.scenes.models import SceneActionDeclaration

        rnd = SceneRoundFactory()
        participant = SceneRoundParticipantFactory(scene_round=rnd)
        SceneActionDeclaration.objects.create(
            scene_round=rnd, round_number=rnd.round_number, participant=participant, is_pass=True
        )
        with self.assertRaises(IntegrityError):
            SceneActionDeclaration.objects.create(
                scene_round=rnd,
                round_number=rnd.round_number,
                participant=participant,
                is_pass=True,
            )

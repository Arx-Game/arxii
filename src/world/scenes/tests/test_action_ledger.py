"""Tests for the multi-action SceneActionDeclaration ledger (Task 2 of #1351)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import SceneRoundMode, SceneRoundParticipantStatus
from world.scenes.factories import SceneRoundFactory
from world.scenes.models import SceneActionDeclaration, SceneRoundParticipant
from world.scenes.round_services import actions_this_round, distinct_actors_this_round


class ActionLedgerTests(TestCase):
    def setUp(self):
        self.rnd = SceneRoundFactory(mode=SceneRoundMode.POSE_ORDER, round_number=1)
        self.sheet = CharacterSheetFactory()
        self.participant = SceneRoundParticipant.objects.create(
            scene_round=self.rnd,
            character_sheet=self.sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

    def test_multiple_actions_per_participant_allowed(self):
        for _ in range(2):
            SceneActionDeclaration.objects.create(
                scene_round=self.rnd,
                round_number=1,
                participant=self.participant,
                is_immediate=True,
                is_pass=False,
            )
        self.assertEqual(actions_this_round(self.rnd, self.participant), 2)
        self.assertEqual(distinct_actors_this_round(self.rnd), 1)

    def test_target_persona_stored(self):
        """target_persona FK can be set and retrieved."""
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        decl = SceneActionDeclaration.objects.create(
            scene_round=self.rnd,
            round_number=1,
            participant=self.participant,
            is_immediate=True,
            is_pass=False,
            target_persona=persona,
        )
        decl.refresh_from_db()
        self.assertEqual(decl.target_persona_id, persona.pk)

    def test_helpers_across_multiple_participants(self):
        """distinct_actors_this_round counts unique participants, not rows."""
        sheet2 = CharacterSheetFactory()
        participant2 = SceneRoundParticipant.objects.create(
            scene_round=self.rnd,
            character_sheet=sheet2,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        # participant 1 gets 2 actions, participant 2 gets 1
        for _ in range(2):
            SceneActionDeclaration.objects.create(
                scene_round=self.rnd,
                round_number=1,
                participant=self.participant,
                is_immediate=True,
                is_pass=False,
            )
        SceneActionDeclaration.objects.create(
            scene_round=self.rnd,
            round_number=1,
            participant=participant2,
            is_immediate=True,
            is_pass=False,
        )
        self.assertEqual(actions_this_round(self.rnd, self.participant), 2)
        self.assertEqual(actions_this_round(self.rnd, participant2), 1)
        self.assertEqual(distinct_actors_this_round(self.rnd), 2)

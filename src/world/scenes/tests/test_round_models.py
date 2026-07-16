from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory
from world.combat.models import CombatEncounter
from world.scenes.constants import RoundStatus, SceneRoundParticipantStatus
from world.scenes.factories import SceneRoundFactory
from world.scenes.models import SceneRound, SceneRoundParticipant
from world.scenes.round_models import AbstractRound


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
        self.room = ObjectDBFactory(db_key="TestRoom")

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
    def test_scene_action_declaration_allows_multiple_rows_per_participant_per_round(self):
        """Multiple declarations per (scene_round, round_number, participant) are now allowed.

        Task 2 removed the one_scene_action_declaration_per_round UniqueConstraint to support
        multi-action rounds (pose-order / max_actions_per_round > 1).  A participant may have
        several is_immediate=True rows (pose-order actions already resolved) alongside a single
        deferred is_immediate=False row (STRICT-style declaration or pass).
        """
        from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
        from world.scenes.models import SceneActionDeclaration

        rnd = SceneRoundFactory()
        participant = SceneRoundParticipantFactory(scene_round=rnd)
        SceneActionDeclaration.objects.create(
            scene_round=rnd,
            round_number=rnd.round_number,
            participant=participant,
            is_immediate=True,
            is_pass=False,
        )
        # A second immediate row (another pose-order action) must be allowed.
        SceneActionDeclaration.objects.create(
            scene_round=rnd,
            round_number=rnd.round_number,
            participant=participant,
            is_immediate=True,
            is_pass=False,
        )
        self.assertEqual(
            SceneActionDeclaration.objects.filter(
                scene_round=rnd, round_number=rnd.round_number, participant=participant
            ).count(),
            2,
        )


class AbstractRoundInheritanceTests(TestCase):
    """SceneRound and CombatEncounter both inherit AbstractRound."""

    def test_scene_round_is_subclass_of_abstract_round(self):
        assert issubclass(SceneRound, AbstractRound)

    def test_combat_encounter_is_subclass_of_abstract_round(self):
        assert issubclass(CombatEncounter, AbstractRound)

    def test_scene_round_exposes_lifecycle_fields(self):
        rnd = SceneRoundFactory()
        for field in ("round_number", "status", "round_started_at", "created_at", "completed_at"):
            assert hasattr(rnd, field), f"SceneRound missing field: {field}"

    def test_combat_encounter_exposes_lifecycle_fields(self):
        enc = CombatEncounterFactory()
        for field in ("round_number", "status", "round_started_at", "created_at", "completed_at"):
            assert hasattr(enc, field), f"CombatEncounter missing field: {field}"

    def test_scene_round_status_default(self):
        rnd = SceneRoundFactory()
        assert rnd.status == RoundStatus.BETWEEN_ROUNDS

    def test_combat_encounter_status_default(self):
        enc = CombatEncounterFactory()
        assert enc.status == RoundStatus.BETWEEN_ROUNDS

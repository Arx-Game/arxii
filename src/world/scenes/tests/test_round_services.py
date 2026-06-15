from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.scenes.constants import RoundStatus, SceneRoundStartReason
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.models import SceneActionDeclaration
from world.scenes.round_services import (
    advance_scene_round,
    end_scene_round,
    maybe_resolve_scene_round,
    resolve_scene_round,
    scene_round_is_complete,
    start_scene_round,
)


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

    def test_action_tick_advances_round_and_ticks_dot(self):
        from world.scenes.round_services import advance_scene_round_for_action

        rnd = SceneRoundFactory(
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(
            target=sheet.character, condition=template, rounds_remaining=3
        )
        advance_scene_round_for_action(rnd)
        inst.refresh_from_db()
        assert inst.rounds_remaining == 2
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.BETWEEN_ROUNDS  # opt-in round stays active

    def test_danger_round_ends_when_no_bleedout_remains(self):
        from world.scenes.round_services import advance_scene_round_for_action

        rnd = SceneRoundFactory(
            status=RoundStatus.BETWEEN_ROUNDS,
            start_reason=SceneRoundStartReason.DANGER,
        )
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        advance_scene_round_for_action(rnd)  # nobody Bleeding-Out -> danger round ends
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.COMPLETED


class SceneRoundResolutionTests(TestCase):
    def setUp(self):
        from evennia_extensions.factories import ObjectDBFactory

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.rnd = SceneRoundFactory(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )

    def _participant(self, *, present: bool, initiative_order: int = 0):
        sheet = CharacterSheetFactory()
        if present:
            sheet.character.db_location = self.room
            sheet.character.save(update_fields=["db_location"])
        return SceneRoundParticipantFactory(
            scene_round=self.rnd,
            character_sheet=sheet,
            initiative_order=initiative_order,
        )

    def _declare_pass(self, participant):
        return SceneActionDeclaration.objects.create(
            scene_round=self.rnd,
            round_number=self.rnd.round_number,
            participant=participant,
            is_pass=True,
        )

    def test_not_complete_when_present_participant_undeclared(self):
        p1 = self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)
        self._declare_pass(p1)  # only one of two present participants has declared
        assert scene_round_is_complete(self.rnd) is False

    def test_complete_when_absent_participant_is_implicit_pass(self):
        present = self._participant(present=True, initiative_order=0)
        self._participant(present=False, initiative_order=1)  # absent => implicit pass
        self._declare_pass(present)
        assert scene_round_is_complete(self.rnd) is True

    def test_not_complete_when_no_one_present(self):
        self._participant(present=False, initiative_order=0)
        self._participant(present=False, initiative_order=1)
        # Nobody present to drive resolution.
        assert scene_round_is_complete(self.rnd) is False

    def test_not_complete_when_present_have_not_declared(self):
        self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)
        assert scene_round_is_complete(self.rnd) is False

    def test_resolve_pass_only_advances_round_and_clears_bridge_rows(self):
        p1 = self._participant(present=True, initiative_order=0)
        p2 = self._participant(present=True, initiative_order=1)
        self._declare_pass(p1)
        self._declare_pass(p2)
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(
            target=p1.character_sheet.character, condition=template, rounds_remaining=3
        )

        resolve_scene_round(self.rnd)

        assert SceneActionDeclaration.objects.filter(scene_round=self.rnd).count() == 0
        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.DECLARING
        assert self.rnd.round_number == 2
        inst.refresh_from_db()
        assert inst.rounds_remaining == 2  # shared END tick fired

    def test_force_resolves_when_present_not_all_declared(self):
        # A GM force-resolve calls resolve_scene_round directly to resolve an incomplete
        # round (undeclared present participants are swept as implicit passes).
        p1 = self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)  # never declares
        self._declare_pass(p1)
        assert scene_round_is_complete(self.rnd) is False

        resolve_scene_round(self.rnd)

        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.DECLARING
        assert self.rnd.round_number == 2
        assert SceneActionDeclaration.objects.filter(scene_round=self.rnd).count() == 0

    def test_resolve_rejects_non_declaring_round(self):
        self.rnd.status = RoundStatus.BETWEEN_ROUNDS
        self.rnd.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            resolve_scene_round(self.rnd)

    def test_maybe_resolve_is_noop_when_incomplete(self):
        p1 = self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)  # undeclared
        self._declare_pass(p1)

        maybe_resolve_scene_round(self.rnd)

        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.DECLARING
        assert self.rnd.round_number == 1  # unchanged
        assert SceneActionDeclaration.objects.filter(scene_round=self.rnd).count() == 1

    def test_maybe_resolve_resolves_when_complete(self):
        p1 = self._participant(present=True, initiative_order=0)
        p2 = self._participant(present=True, initiative_order=1)
        self._declare_pass(p1)
        self._declare_pass(p2)

        maybe_resolve_scene_round(self.rnd)

        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.DECLARING
        assert self.rnd.round_number == 2
        assert SceneActionDeclaration.objects.filter(scene_round=self.rnd).count() == 0

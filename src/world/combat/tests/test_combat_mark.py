"""Tests for the CombatMark model — the Fulmination mark (#2664)."""

from django.db import IntegrityError
from django.test import TestCase
from drf_spectacular.drainage import get_override
from rest_framework.serializers import ListSerializer

from world.combat.constants import OpponentStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatMark
from world.combat.serializers import CombatMarkSerializer, EncounterDetailSerializer
from world.combat.services import declare_mark
from world.scenes.constants import RoundStatus


class CombatMarkModelTest(TestCase):
    """CombatMark creation, uniqueness, and cascade behavior."""

    def setUp(self):
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

    def test_create_combat_mark(self):
        mark = CombatMark.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            opponent=self.opponent,
            round_number=1,
        )
        self.assertEqual(mark.opponent, self.opponent)
        self.assertEqual(mark.round_number, 1)
        self.assertIsNone(mark.source_technique)

    def test_unique_per_participant_round(self):
        CombatMark.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            opponent=self.opponent,
            round_number=1,
        )
        with self.assertRaises(IntegrityError):
            CombatMark.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                opponent=self.opponent,
                round_number=1,
            )

    def test_different_participants_can_mark_same_round(self):
        other_participant = CombatParticipantFactory(encounter=self.encounter)
        CombatMark.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            opponent=self.opponent,
            round_number=1,
        )
        CombatMark.objects.create(
            encounter=self.encounter,
            participant=other_participant,
            opponent=self.opponent,
            round_number=1,
        )
        self.assertEqual(CombatMark.objects.count(), 2)

    def test_same_participant_different_rounds(self):
        CombatMark.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            opponent=self.opponent,
            round_number=1,
        )
        CombatMark.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            opponent=self.opponent,
            round_number=2,
        )
        self.assertEqual(CombatMark.objects.count(), 2)


class DeclareMarkServiceTest(TestCase):
    """declare_mark validation gates and happy path."""

    def setUp(self):
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

    def test_declare_mark_creates_mark(self):
        mark = declare_mark(self.participant, self.opponent)
        self.assertEqual(mark.participant, self.participant)
        self.assertEqual(mark.opponent, self.opponent)
        self.assertEqual(mark.round_number, self.encounter.round_number)
        self.assertIsNone(mark.source_technique)

    def test_declare_mark_rejects_non_declaring_status(self):
        self.encounter.status = RoundStatus.RESOLVING
        self.encounter.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            declare_mark(self.participant, self.opponent)

    def test_declare_mark_rejects_inactive_participant(self):
        self.participant.status = ParticipantStatus.FLED
        self.participant.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            declare_mark(self.participant, self.opponent)

    def test_declare_mark_rejects_defeated_opponent(self):
        self.opponent.status = OpponentStatus.DEFEATED
        self.opponent.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            declare_mark(self.participant, self.opponent)

    def test_declare_mark_rejects_wrong_encounter_opponent(self):
        other_encounter = CombatEncounterFactory()
        other_opponent = CombatOpponentFactory(encounter=other_encounter)
        with self.assertRaises(ValueError):
            declare_mark(self.participant, other_opponent)

    def test_declare_mark_is_idempotent_per_round(self):
        mark1 = declare_mark(self.participant, self.opponent)
        mark2 = declare_mark(self.participant, self.opponent)
        self.assertEqual(mark1.pk, mark2.pk)
        self.assertEqual(CombatMark.objects.count(), 1)


def _serialize(encounter: object) -> dict:
    if not hasattr(encounter, "participants_cached"):
        encounter.participants_cached = list(encounter.participants.all())
    if not hasattr(encounter, "opponents_cached"):
        encounter.opponents_cached = list(encounter.opponents.all())
    return EncounterDetailSerializer(encounter, context={}).data


class EncounterMarksPayloadTest(TestCase):
    """EncounterDetail ``marks``: this round's marks, public to every reader (#4603)."""

    def setUp(self):
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=2)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

    def _mark(self, round_number: int) -> CombatMark:
        return CombatMark.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            opponent=self.opponent,
            round_number=round_number,
        )

    def test_marks_lists_only_this_rounds_marks(self):
        self._mark(1)
        self._mark(2)
        marks = _serialize(self.encounter)["marks"]
        self.assertEqual([m["round_number"] for m in marks], [2])

    def test_mark_rows_carry_marker_and_target(self):
        mark = self._mark(2)
        marks = _serialize(self.encounter)["marks"]
        self.assertEqual(
            marks,
            [
                {
                    "id": mark.pk,
                    "participant_id": self.participant.pk,
                    "opponent_id": self.opponent.pk,
                    "round_number": 2,
                }
            ],
        )

    def test_marks_is_empty_when_nobody_marked(self):
        self.assertEqual(_serialize(self.encounter)["marks"], [])

    def test_marks_is_typed_in_the_schema(self):
        override = get_override(EncounterDetailSerializer.get_marks, "field")
        self.assertIsInstance(override, ListSerializer)
        self.assertIsInstance(override.child, CombatMarkSerializer)

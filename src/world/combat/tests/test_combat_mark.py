"""Tests for the CombatMark model — the Fulmination mark (#2664)."""

from django.db import IntegrityError
from django.test import TestCase

from world.combat.constants import OpponentStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatMark
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

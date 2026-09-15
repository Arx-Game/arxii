"""DramaticSurgeRecord companion subject (#3575): dedup slice and exclusivity."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import DramaticSurgeRecord
from world.companions.factories import CompanionFactory


class SurgeRecordCompanionSubjectTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        cls.companion = CompanionFactory(owner=cls.participant.character_sheet)

    def _record(self, **kwargs) -> DramaticSurgeRecord:
        return DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=SurgeTriggerKind.ALLY_FALLEN,
            amount=2,
            round_number=1,
            **kwargs,
        )

    def test_one_surge_per_companion_subject(self) -> None:
        self._record(subject_companion=self.companion)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(subject_companion=self.companion)

    def test_companion_subject_does_not_collide_with_subjectless_row(self) -> None:
        self._record(subject_companion=self.companion)
        self._record()  # subject-less slice is separate
        self.assertEqual(DramaticSurgeRecord.objects.count(), 2)

    def test_companion_and_sheet_subject_are_exclusive(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(
                subject_companion=self.companion,
                subject_sheet=self.participant.character_sheet,
            )

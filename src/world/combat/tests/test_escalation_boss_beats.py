"""Boss-beat surge triggers (#3445): dedup columns, curve magnitudes, and the
two boss seams (phase transition / enrage, break-bar break)."""

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from world.combat.constants import SurgeTriggerKind
from world.combat.factories import (
    BossOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import DramaticSurgeRecord


class BossBeatDedupConstraintTests(TestCase):
    """The per-boss-per-phase dedup slice (#3445)."""

    def setUp(self):
        self.participant = CombatParticipantFactory()
        self.encounter = self.participant.encounter
        self.boss = BossOpponentFactory(encounter=self.encounter)

    def _record(self, *, phase_number, opponent=None, trigger_kind=None):
        return DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=trigger_kind or SurgeTriggerKind.BOSS_PHASE,
            subject_sheet=None,
            subject_opponent=opponent or self.boss,
            subject_phase_number=phase_number,
            amount=2,
            round_number=1,
        )

    def test_same_boss_same_phase_is_rejected(self):
        self._record(phase_number=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(phase_number=2)

    def test_same_boss_later_phase_is_allowed(self):
        self._record(phase_number=2)
        self._record(phase_number=3)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 2)

    def test_second_boss_same_phase_is_allowed(self):
        other_boss = BossOpponentFactory(encounter=self.encounter)
        self._record(phase_number=2)
        self._record(phase_number=2, opponent=other_boss)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 2)

    def test_high_stakes_still_one_shot_per_encounter(self):
        DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
            subject_sheet=None,
            amount=2,
            round_number=1,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DramaticSurgeRecord.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                trigger_kind=SurgeTriggerKind.HIGH_STAKES,
                subject_sheet=None,
                amount=2,
                round_number=4,
            )

    def test_boss_row_requires_a_phase_number(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DramaticSurgeRecord.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                trigger_kind=SurgeTriggerKind.BOSS_BREAK,
                subject_sheet=None,
                subject_opponent=self.boss,
                subject_phase_number=None,
                amount=4,
                round_number=1,
            )


@override_settings(SEED_SAMPLE_CONTENT=True)  # EscalationCurveFactory gates on #2698
class BossBeatCurveFieldTests(TestCase):
    def test_curve_carries_the_three_boss_magnitudes(self):
        curve = EscalationCurveFactory()
        self.assertEqual(curve.boss_phase_spike_intensity_amount, 2)
        self.assertEqual(curve.boss_enrage_spike_intensity_amount, 4)
        self.assertEqual(curve.boss_break_spike_intensity_amount, 4)

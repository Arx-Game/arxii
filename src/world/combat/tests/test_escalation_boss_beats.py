"""Boss-beat surge triggers (#3445): dedup columns, curve magnitudes, and the
two boss seams (phase transition / enrage, break-bar break)."""

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import apply_boss_break_surge, apply_boss_phase_surge
from world.combat.factories import (
    BossOpponentFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement


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


@override_settings(SEED_SAMPLE_CONTENT=True)  # EscalationCurveFactory gates on #2698
class BossBeatSurgeLegTests(TestCase):
    """apply_boss_phase_surge / apply_boss_break_surge (#3445)."""

    def setUp(self):
        self.curve = EscalationCurveFactory(
            boss_phase_spike_intensity_amount=2,
            boss_enrage_spike_intensity_amount=4,
            boss_break_spike_intensity_amount=5,
        )
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve, round_number=3)
        self.boss = BossOpponentFactory(encounter=self.encounter, current_phase=2)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.character = self.participant.character_sheet.character
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)

    def _intensity(self) -> int:
        return CharacterEngagement.objects.get(
            character=self.character.sheet_data
        ).intensity_modifier

    def test_plain_transition_surges_boss_phase(self):
        apply_boss_phase_surge(opponent=self.boss, enraged=False)

        self.assertEqual(self._intensity(), 2)
        record = DramaticSurgeRecord.objects.get()
        self.assertEqual(record.trigger_kind, SurgeTriggerKind.BOSS_PHASE)
        self.assertEqual(record.subject_opponent_id, self.boss.pk)
        self.assertEqual(record.subject_phase_number, 2)

    def test_enraging_transition_surges_boss_enrage(self):
        apply_boss_phase_surge(opponent=self.boss, enraged=True)

        self.assertEqual(self._intensity(), 4)
        self.assertEqual(
            DramaticSurgeRecord.objects.get().trigger_kind, SurgeTriggerKind.BOSS_ENRAGE
        )

    def test_break_surge_repeats_once_per_phase(self):
        apply_boss_break_surge(opponent=self.boss)
        apply_boss_break_surge(opponent=self.boss)  # the #2642 re-break: no-op

        self.assertEqual(self._intensity(), 5)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 1)

        self.boss.current_phase = 3
        self.boss.save(update_fields=["current_phase"])
        apply_boss_break_surge(opponent=self.boss)

        self.assertEqual(self._intensity(), 10)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 2)

    def test_no_curve_surges_nobody(self):
        plain = CombatEncounterFactory(escalation_curve=None, round_number=3)
        boss = BossOpponentFactory(encounter=plain)
        participant = CombatParticipantFactory(encounter=plain, status=ParticipantStatus.ACTIVE)
        begin_engagement(participant.character_sheet.character, EngagementType.COMBAT, source=plain)

        apply_boss_phase_surge(opponent=boss, enraged=True)

        self.assertFalse(DramaticSurgeRecord.objects.filter(encounter=plain).exists())

    def test_zero_authored_amount_surges_nobody(self):
        self.curve.boss_phase_spike_intensity_amount = 0
        self.curve.save(update_fields=["boss_phase_spike_intensity_amount"])

        apply_boss_phase_surge(opponent=self.boss, enraged=False)

        self.assertEqual(self._intensity(), 0)
        self.assertFalse(DramaticSurgeRecord.objects.exists())

    def test_only_active_participants_surge(self):
        fled = CombatParticipantFactory(encounter=self.encounter, status=ParticipantStatus.FLED)
        begin_engagement(
            fled.character_sheet.character, EngagementType.COMBAT, source=self.encounter
        )

        apply_boss_phase_surge(opponent=self.boss, enraged=False)

        self.assertFalse(DramaticSurgeRecord.objects.filter(participant=fled).exists())

"""Boss-beat surge triggers (#3445): dedup columns, curve magnitudes, and the
two boss seams (phase transition / enrage, break-bar break)."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import apply_boss_break_surge, apply_boss_phase_surge
from world.combat.factories import (
    BossOpponentFactory,
    BossPhaseFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.services import assess_break_bar, check_and_advance_boss_phase
from world.combat.types import ActionOutcome, OpponentDamageResult
from world.magic.factories import EffectTypeFactory
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


@override_settings(SEED_SAMPLE_CONTENT=True)  # EscalationCurveFactory gates on #2698
class BossPhaseSeamTests(TestCase):
    """check_and_advance_boss_phase fires the right surge (#3445)."""

    def setUp(self):
        self.curve = EscalationCurveFactory(
            boss_phase_spike_intensity_amount=2,
            boss_enrage_spike_intensity_amount=6,
        )
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve, round_number=3)
        self.boss = BossOpponentFactory(
            encounter=self.encounter, health=40, max_health=100, current_phase=1
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        begin_engagement(
            self.participant.character_sheet.character,
            EngagementType.COMBAT,
            source=self.encounter,
        )

    def test_plain_transition_records_boss_phase(self):
        BossPhaseFactory(
            opponent=self.boss,
            phase_number=2,
            health_trigger_percentage=0.5,
            damage_multiplier=Decimal("1.0"),
        )

        self.assertIsNotNone(check_and_advance_boss_phase(self.boss))

        record = DramaticSurgeRecord.objects.get()
        self.assertEqual(record.trigger_kind, SurgeTriggerKind.BOSS_PHASE)
        self.assertEqual(record.subject_phase_number, 2)
        self.assertEqual(record.amount, 2)

    def test_enraging_transition_records_boss_enrage_only(self):
        BossPhaseFactory(
            opponent=self.boss,
            phase_number=2,
            health_trigger_percentage=0.5,
            damage_multiplier=Decimal("2.5"),
        )

        check_and_advance_boss_phase(self.boss)

        record = DramaticSurgeRecord.objects.get()
        self.assertEqual(record.trigger_kind, SurgeTriggerKind.BOSS_ENRAGE)
        self.assertEqual(record.amount, 6)

    def test_no_transition_surges_nobody(self):
        BossPhaseFactory(
            opponent=self.boss,
            phase_number=2,
            health_trigger_percentage=0.1,
            damage_multiplier=Decimal("2.5"),
        )

        self.assertIsNone(check_and_advance_boss_phase(self.boss))
        self.assertFalse(DramaticSurgeRecord.objects.exists())


@override_settings(SEED_SAMPLE_CONTENT=True)  # EscalationCurveFactory gates on #2698
class BossBreakSeamTests(TestCase):
    """assess_break_bar fires BOSS_BREAK once per phase (#3445)."""

    def setUp(self):
        self.curve = EscalationCurveFactory(boss_break_spike_intensity_amount=5)
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve, round_number=2)
        self.boss = BossOpponentFactory(
            encounter=self.encounter,
            current_phase=1,
            break_bar_threshold=1,
            break_bar_current=1,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.character = self.participant.character_sheet.character
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)

    def _damage_outcome(self):
        """One PC DAMAGE feed against the boss - the cheapest qualifying event.

        Mirrors ``world/combat/tests/test_break_bar.py``'s ``_dmg_result`` idiom:
        ``_break_bar_events_this_round`` needs ``entity_type == "pc"``, a
        ``damage_results`` entry carrying the boss pk, and non-null
        ``participant_id`` / ``effect_type_id``.
        """
        return ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            damage_results=[
                OpponentDamageResult(
                    damage_dealt=10,
                    health_damaged=True,
                    probed=False,
                    probing_increment=0,
                    defeated=False,
                    opponent_id=self.boss.pk,
                )
            ],
            participant_id=self.participant.pk,
            effect_type_id=EffectTypeFactory().pk,
        )

    def _intensity(self) -> int:
        return CharacterEngagement.objects.get(
            character=self.character.sheet_data
        ).intensity_modifier

    def test_break_surges_every_active_pc(self):
        assess_break_bar(self.encounter, [self._damage_outcome()])

        self.boss.refresh_from_db()
        self.assertEqual(self.boss.break_bar_current, 0)
        record = DramaticSurgeRecord.objects.get()
        self.assertEqual(record.trigger_kind, SurgeTriggerKind.BOSS_BREAK)
        self.assertEqual(record.subject_opponent_id, self.boss.pk)
        self.assertEqual(record.subject_phase_number, 1)
        self.assertEqual(self._intensity(), 5)

    def test_rebreak_in_the_same_phase_does_not_surge_again(self):
        assess_break_bar(self.encounter, [self._damage_outcome()])

        # The #2642 re-break: the window closes, the bar is still at zero, and the
        # next qualifying feed re-opens the window and re-broadcasts the break.
        self.boss.refresh_from_db()
        self.boss.vulnerability_rounds_remaining = 0
        self.boss.save(update_fields=["vulnerability_rounds_remaining"])
        assess_break_bar(self.encounter, [self._damage_outcome()])

        self.assertEqual(DramaticSurgeRecord.objects.count(), 1)
        self.assertEqual(self._intensity(), 5)

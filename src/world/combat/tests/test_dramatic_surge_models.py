"""Model-layer tests for the dramatic surge engine (#2013): dedup constraints,
new EscalationCurve fields, and StakesEscalationModifier."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import StakesLevel, SurgeTriggerKind
from world.combat.factories import (
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import DramaticSurgeRecord, StakesEscalationModifier


class DramaticSurgeRecordDedupTests(TestCase):
    def setUp(self):
        self.participant = CombatParticipantFactory()
        self.encounter = self.participant.encounter
        self.subject_sheet = CharacterSheetFactory()

    def test_duplicate_with_subject_is_rejected(self):
        DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=SurgeTriggerKind.ALLY_PERIL,
            subject_sheet=self.subject_sheet,
            amount=3,
            round_number=1,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DramaticSurgeRecord.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                trigger_kind=SurgeTriggerKind.ALLY_PERIL,
                subject_sheet=self.subject_sheet,
                amount=3,
                round_number=2,
            )

    def test_duplicate_without_subject_is_rejected(self):
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
                round_number=3,
            )

    def test_different_subject_is_allowed(self):
        other_subject = CharacterSheetFactory()
        DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=SurgeTriggerKind.HATED_FOE,
            subject_sheet=self.subject_sheet,
            amount=3,
            round_number=1,
        )
        # Does not raise: different subject_sheet.
        DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=SurgeTriggerKind.HATED_FOE,
            subject_sheet=other_subject,
            amount=3,
            round_number=1,
        )
        self.assertEqual(DramaticSurgeRecord.objects.count(), 2)

    def test_different_trigger_kind_is_allowed(self):
        DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=SurgeTriggerKind.ALLY_PERIL,
            subject_sheet=self.subject_sheet,
            amount=3,
            round_number=1,
        )
        # Same subject, different kind: allowed (peril once, fall is separate).
        DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=SurgeTriggerKind.ALLY_FALLEN,
            subject_sheet=self.subject_sheet,
            amount=3,
            round_number=2,
        )
        self.assertEqual(DramaticSurgeRecord.objects.count(), 2)


class EscalationCurveNewFieldsTests(TestCase):
    def test_new_fields_have_documented_defaults(self):
        curve = EscalationCurveFactory()
        self.assertEqual(curve.peril_spike_intensity_amount, 3)
        self.assertEqual(curve.hated_foe_spike_intensity_amount, 3)
        self.assertEqual(curve.surge_narration, "")


class StakesEscalationModifierTests(TestCase):
    def test_unique_per_stakes_level(self):
        StakesEscalationModifier.objects.create(stakes_level=StakesLevel.REGIONAL)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StakesEscalationModifier.objects.create(stakes_level=StakesLevel.REGIONAL)

    def test_default_curve_nullable(self):
        modifier = StakesEscalationModifier.objects.create(stakes_level=StakesLevel.LOCAL)
        self.assertIsNone(modifier.default_curve)

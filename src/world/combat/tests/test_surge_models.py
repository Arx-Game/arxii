"""Models behind rolled dramatic surges (#4737)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.forms import inlineformset_factory
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.admin import SurgeDegreeBandFormSet
from world.combat.constants import ROLLED_SURGE_TRIGGER_KINDS, SurgeTriggerKind
from world.combat.factories import (
    CombatParticipantFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import DramaticSurgeRecord, SurgeDegreeBand, SurgeTuning
from world.traits.factories import CheckOutcomeFactory


class SurgeTuningModelTests(TestCase):
    def test_rolled_kinds_are_the_three_new_members(self) -> None:
        self.assertEqual(
            set(ROLLED_SURGE_TRIGGER_KINDS),
            {
                SurgeTriggerKind.TAUNT_RECEIVED,
                SurgeTriggerKind.RALLIED,
                SurgeTriggerKind.ALLY_HURT,
            },
        )

    def test_tuning_kind_unique(self) -> None:
        SurgeTuningFactory(trigger_kind=SurgeTriggerKind.RALLIED)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SurgeTuningFactory(trigger_kind=SurgeTriggerKind.RALLIED)

    def test_band_unique_per_tuning_outcome(self) -> None:
        tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.ALLY_HURT)
        outcome = CheckOutcomeFactory(name="Surge Unique Outcome", success_level=1)
        SurgeDegreeBandFactory(tuning=tuning, outcome=outcome)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SurgeDegreeBandFactory(tuning=tuning, outcome=outcome)

    def test_band_clean_checks_against_sibling_bands(self) -> None:
        tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED)
        low = CheckOutcomeFactory(name="Surge Clean Low", success_level=-1)
        high = CheckOutcomeFactory(name="Surge Clean High", success_level=2)
        SurgeDegreeBandFactory(tuning=tuning, outcome=low, intensity=5)
        bad = SurgeDegreeBandFactory.build(tuning=tuning, outcome=high, intensity=1)
        with self.assertRaises(ValidationError):
            bad.clean()


class DramaticSurgeRecordRepeatTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.participant = CombatParticipantFactory()
        cls.encounter = cls.participant.encounter
        cls.sheet = CharacterSheetFactory()

    def _record(self, kind: str, *, repeat_round: int | None, sheet=None, round_number=1):
        return DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=kind,
            subject_sheet=sheet,
            amount=2,
            round_number=round_number,
            repeat_round=repeat_round,
        )

    def test_record_repeat_round_allows_second_round_blocks_same_round(self) -> None:
        self._record(SurgeTriggerKind.ALLY_HURT, repeat_round=1, sheet=self.sheet)
        self._record(SurgeTriggerKind.ALLY_HURT, repeat_round=2, sheet=self.sheet, round_number=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(SurgeTriggerKind.ALLY_HURT, repeat_round=2, sheet=self.sheet)

    def test_record_repeat_round_without_subject_blocks_same_round(self) -> None:
        self._record(SurgeTriggerKind.TAUNT_RECEIVED, repeat_round=1)
        self._record(SurgeTriggerKind.TAUNT_RECEIVED, repeat_round=2, round_number=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(SurgeTriggerKind.TAUNT_RECEIVED, repeat_round=2)

    def test_record_old_kinds_still_once_per_encounter(self) -> None:
        self._record(SurgeTriggerKind.ALLY_PERIL, repeat_round=None, sheet=self.sheet)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(
                SurgeTriggerKind.ALLY_PERIL,
                repeat_round=None,
                sheet=self.sheet,
                round_number=2,
            )

    def test_record_new_fields_default(self) -> None:
        record = self._record(SurgeTriggerKind.HIGH_STAKES, repeat_round=None)
        self.assertEqual(record.control_change, 0)
        self.assertIsNone(record.outcome)
        self.assertIsNone(record.potency)


class TauntEntryTests(TestCase):
    def test_taunt_entry_cannot_carry_damage(self) -> None:
        entry = ThreatPoolEntryFactory.build(base_damage=5, taunt_potency=3)
        with self.assertRaises(ValidationError) as ctx:
            entry.clean()
        self.assertIn("taunt_potency", ctx.exception.message_dict)

    def test_taunt_entry_with_no_damage_is_valid(self) -> None:
        entry = ThreatPoolEntryFactory.build(base_damage=0, taunt_potency=3)
        entry.clean()


class SurgeBandInlineFormSetTests(TestCase):
    def _formset(self, rows: list[dict]):
        tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.RALLIED)
        formset_cls = inlineformset_factory(
            SurgeTuning,
            SurgeDegreeBand,
            formset=SurgeDegreeBandFormSet,
            fields=["outcome", "intensity", "control_change", "condition"],
            extra=len(rows),
        )
        data = {
            "bands-TOTAL_FORMS": str(len(rows)),
            "bands-INITIAL_FORMS": "0",
            "bands-MIN_NUM_FORMS": "0",
            "bands-MAX_NUM_FORMS": "1000",
        }
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"bands-{index}-{key}"] = str(value)
        return formset_cls(data, instance=tuning, prefix="bands")

    def test_inline_rejects_non_monotonic_set(self) -> None:
        worse = CheckOutcomeFactory(name="Surge Inline Worse", success_level=-1)
        better = CheckOutcomeFactory(name="Surge Inline Better", success_level=2)
        formset = self._formset(
            [
                {"outcome": worse.pk, "intensity": 5, "control_change": 0},
                {"outcome": better.pk, "intensity": 1, "control_change": 0},
            ]
        )
        self.assertFalse(formset.is_valid())
        self.assertTrue(formset.non_form_errors())

    def test_inline_accepts_monotonic_set(self) -> None:
        worse = CheckOutcomeFactory(name="Surge Inline Ok Worse", success_level=-1)
        better = CheckOutcomeFactory(name="Surge Inline Ok Better", success_level=2)
        formset = self._formset(
            [
                {"outcome": worse.pk, "intensity": 1, "control_change": 0},
                {"outcome": better.pk, "intensity": 4, "control_change": 1},
            ]
        )
        self.assertTrue(formset.is_valid(), formset.errors)

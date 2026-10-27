"""Models behind rolled dramatic surges (#4737)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.forms import inlineformset_factory
from django.test import TestCase, tag

from actions.factories import ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.admin import SurgeDegreeBandForm, SurgeDegreeBandFormSet
from world.combat.constants import SurgeTriggerKind
from world.combat.factories import (
    CombatOpponentFactory,
    CombatParticipantFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import DramaticSurgeRecord, SurgeDegreeBand, SurgeTuning
from world.companions.factories import CompanionFactory
from world.conditions.factories import ConditionTemplateFactory
from world.traits.factories import CheckOutcomeFactory


class SurgeTuningModelTests(TestCase):
    """Kept: the tuning and band validators are branches only the admin form reaches."""

    def test_clean_rejects_potency_on_a_kind_that_never_reads_it(self) -> None:
        for kind in (SurgeTriggerKind.TAUNT_RECEIVED, SurgeTriggerKind.RALLIED):
            for field_name in ("potency_base", "potency_per_depth"):
                with self.subTest(kind=kind, field=field_name):
                    tuning = SurgeTuningFactory.build(trigger_kind=kind, **{field_name: 3})
                    with self.assertRaises(ValidationError) as ctx:
                        tuning.clean()
                    self.assertIn(field_name, ctx.exception.message_dict)

    def test_clean_accepts_potency_on_ally_hurt_and_zero_elsewhere(self) -> None:
        SurgeTuningFactory.build(
            trigger_kind=SurgeTriggerKind.ALLY_HURT, potency_base=4, potency_per_depth=2
        ).clean()
        SurgeTuningFactory.build(
            trigger_kind=SurgeTriggerKind.RALLIED, potency_base=0, potency_per_depth=0
        ).clean()

    def test_band_clean_checks_against_sibling_bands(self) -> None:
        tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED)
        low = CheckOutcomeFactory(name="Surge Clean Low", success_level=-1)
        high = CheckOutcomeFactory(name="Surge Clean High", success_level=2)
        SurgeDegreeBandFactory(tuning=tuning, outcome=low, intensity=5)
        bad = SurgeDegreeBandFactory.build(tuning=tuning, outcome=high, intensity=1)
        with self.assertRaises(ValidationError):
            bad.clean()


class DramaticSurgeRecordRepeatTests(TestCase):
    """Kept: the dedup uniques and CheckConstraints are database invariants no played round
    breaks, and the one thing that stops a double surge."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.participant = CombatParticipantFactory()
        cls.encounter = cls.participant.encounter
        cls.sheet = CharacterSheetFactory()
        cls.outcome = CheckOutcomeFactory(name="Surge Record Outcome", success_level=1)

    def _record(self, kind: str, *, repeat_round: int | None, sheet=None, round_number=1):
        return DramaticSurgeRecord.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=kind,
            subject_sheet=sheet,
            amount=2,
            round_number=round_number,
            repeat_round=repeat_round,
            outcome=self.outcome if repeat_round is not None else None,
        )

    @tag("postgres")  # nulls_distinct=False is unenforced on SQLite
    def test_record_repeat_round_allows_second_round_blocks_same_round(self) -> None:
        self._record(SurgeTriggerKind.ALLY_HURT, repeat_round=1, sheet=self.sheet)
        self._record(SurgeTriggerKind.ALLY_HURT, repeat_round=2, sheet=self.sheet, round_number=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(
                SurgeTriggerKind.ALLY_HURT, repeat_round=2, sheet=self.sheet, round_number=2
            )

    @tag("postgres")  # nulls_distinct=False is unenforced on SQLite
    def test_record_repeat_round_without_subject_blocks_same_round(self) -> None:
        self._record(SurgeTriggerKind.TAUNT_RECEIVED, repeat_round=1)
        self._record(SurgeTriggerKind.TAUNT_RECEIVED, repeat_round=2, round_number=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(SurgeTriggerKind.TAUNT_RECEIVED, repeat_round=2, round_number=2)

    def test_record_old_kinds_still_once_per_encounter(self) -> None:
        self._record(SurgeTriggerKind.ALLY_PERIL, repeat_round=None, sheet=self.sheet)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(
                SurgeTriggerKind.ALLY_PERIL,
                repeat_round=None,
                sheet=self.sheet,
                round_number=2,
            )

    def test_record_repeat_round_must_equal_the_round_number(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(SurgeTriggerKind.TAUNT_RECEIVED, repeat_round=2, round_number=1)

    def test_record_rolled_needs_an_outcome_and_an_old_kind_has_none(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            DramaticSurgeRecord.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED,
                amount=2,
                round_number=1,
                repeat_round=1,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DramaticSurgeRecord.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                trigger_kind=SurgeTriggerKind.HIGH_STAKES,
                amount=2,
                round_number=1,
                outcome=self.outcome,
            )


class TauntEntryTests(TestCase):
    """Kept: ``ThreatPoolEntry.clean`` rejects shapes the admin form can submit."""

    def test_taunt_entry_cannot_carry_damage(self) -> None:
        entry = ThreatPoolEntryFactory.build(base_damage=5, taunt_potency=3)
        with self.assertRaises(ValidationError) as ctx:
            entry.clean()
        self.assertIn("taunt_potency", ctx.exception.message_dict)

    def test_taunt_entry_cannot_carry_a_defense_check_or_on_hit_pool(self) -> None:
        entry = ThreatPoolEntryFactory(
            base_damage=0,
            taunt_potency=3,
            defense_check_type=CheckTypeFactory(),
            on_hit_consequence_pool=ConsequencePoolFactory(),
        )
        with self.assertRaises(ValidationError) as ctx:
            entry.clean()
        self.assertIn("defense_check_type", ctx.exception.message_dict)
        self.assertIn("on_hit_consequence_pool", ctx.exception.message_dict)

    def test_taunt_entry_cannot_apply_conditions(self) -> None:
        entry = ThreatPoolEntryFactory(base_damage=0, taunt_potency=3)
        entry.conditions_applied.add(ConditionTemplateFactory())
        with self.assertRaises(ValidationError) as ctx:
            entry.clean()
        self.assertIn("conditions_applied", ctx.exception.message_dict)

    def test_attack_entry_may_carry_a_defense_check(self) -> None:
        ThreatPoolEntryFactory(
            base_damage=5, taunt_potency=None, defense_check_type=CheckTypeFactory()
        ).clean()

    def test_taunt_entry_with_no_damage_is_valid(self) -> None:
        entry = ThreatPoolEntryFactory.build(base_damage=0, taunt_potency=3)
        entry.clean()


class SurgeBandInlineFormSetTests(TestCase):
    """Kept: the admin inline formset is the staff-facing validation of a band set."""

    def _formset(self, rows: list[dict]):
        tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.RALLIED)
        formset_cls = inlineformset_factory(
            SurgeTuning,
            SurgeDegreeBand,
            form=SurgeDegreeBandForm,
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

    def test_inline_edits_two_persisted_bands_together(self) -> None:
        tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.ALLY_HURT)
        worse = CheckOutcomeFactory(name="Surge Persisted Worse", success_level=-1)
        better = CheckOutcomeFactory(name="Surge Persisted Better", success_level=2)
        low = SurgeDegreeBandFactory(tuning=tuning, outcome=worse, intensity=1)
        high = SurgeDegreeBandFactory(tuning=tuning, outcome=better, intensity=4)
        formset = self._persisted_formset(tuning, [(low, 5), (high, 6)])
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        low.refresh_from_db()
        high.refresh_from_db()
        self.assertEqual((low.intensity, high.intensity), (5, 6))

    def test_inline_rejects_violating_persisted_set(self) -> None:
        tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.ALLY_HURT)
        worse = CheckOutcomeFactory(name="Surge Persisted Bad Worse", success_level=-1)
        better = CheckOutcomeFactory(name="Surge Persisted Bad Better", success_level=2)
        low = SurgeDegreeBandFactory(tuning=tuning, outcome=worse, intensity=1)
        high = SurgeDegreeBandFactory(tuning=tuning, outcome=better, intensity=4)
        formset = self._persisted_formset(tuning, [(low, 7), (high, 6)])
        self.assertFalse(formset.is_valid())
        self.assertTrue(formset.non_form_errors())

    def _persisted_formset(self, tuning, edits: list[tuple]):
        formset_cls = inlineformset_factory(
            SurgeTuning,
            SurgeDegreeBand,
            form=SurgeDegreeBandForm,
            formset=SurgeDegreeBandFormSet,
            fields=["outcome", "intensity", "control_change", "condition"],
            extra=0,
        )
        data = {
            "bands-TOTAL_FORMS": str(len(edits)),
            "bands-INITIAL_FORMS": str(len(edits)),
            "bands-MIN_NUM_FORMS": "0",
            "bands-MAX_NUM_FORMS": "1000",
        }
        for index, (band, intensity) in enumerate(edits):
            data[f"bands-{index}-id"] = str(band.pk)
            data[f"bands-{index}-tuning"] = str(tuning.pk)
            data[f"bands-{index}-outcome"] = str(band.outcome_id)
            data[f"bands-{index}-intensity"] = str(intensity)
            data[f"bands-{index}-control_change"] = str(band.control_change)
        return formset_cls(data, instance=tuning, prefix="bands")


class SurgeRolledSubjectCheckTests(TestCase):
    """Kept: the CheckConstraint that keeps a rolled row off boss and companion subjects."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.participant = CombatParticipantFactory()
        cls.encounter = cls.participant.encounter

    def test_rolled_row_with_boss_subject_is_rejected(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DramaticSurgeRecord.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED,
                subject_opponent=opponent,
                subject_phase_number=1,
                amount=2,
                round_number=1,
                repeat_round=1,
                outcome=CheckOutcomeFactory(name="Surge Boss Subject Outcome", success_level=1),
            )

    def test_rolled_row_with_companion_subject_is_rejected(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            DramaticSurgeRecord.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                trigger_kind=SurgeTriggerKind.RALLIED,
                subject_companion=CompanionFactory(owner=self.participant.character_sheet),
                amount=2,
                round_number=1,
                repeat_round=1,
                outcome=CheckOutcomeFactory(name="Surge Companion Outcome", success_level=1),
            )

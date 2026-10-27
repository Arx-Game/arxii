"""The surge-roll core service (#4737): bands, dedup, control, conditions, roll line.

What the played journeys (``integration_tests.test_surge_rolls_journeys``) assert is the
whole path from a typed command or a round to what the player was told. What stays here is
what no journey reaches: pure band selection with its fallbacks, rounding, the dedup key,
collaborator failure and refusal, and the zero-amount and deferred-delivery edges.
"""

import logging
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, override_settings

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ROLLED_SURGE_TRIGGER_KINDS,
    ParticipantStatus,
    SurgeTriggerKind,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.surge_rolls import (
    POTENCY_LABELS,
    apply_rolled_surge,
    band_for_outcome,
    roll_line,
    rolled_surge_possible,
)
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.types import ApplyConditionResult
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.traits.factories import CheckOutcomeFactory

KIND = SurgeTriggerKind.TAUNT_RECEIVED


@override_settings(SEED_SAMPLE_CONTENT=True)  # EscalationCurveFactory gates on #2698
class SurgeRollTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.curve = EscalationCurveFactory(surge_narration="{character} surges.")
        cls.encounter = CombatEncounterFactory(escalation_curve=cls.curve)
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        cls.character = cls.participant.character_sheet.character
        begin_engagement(cls.character, EngagementType.COMBAT, source=cls.encounter)
        cls.check_type = CheckTypeFactory(name="Surge Composure")
        cls.tuning = SurgeTuningFactory(trigger_kind=KIND, check_type=cls.check_type)
        cls.fail = CheckOutcomeFactory(name="Surge Failure", success_level=-1)
        cls.partial = CheckOutcomeFactory(name="Surge Partial", success_level=0)
        cls.success = CheckOutcomeFactory(name="Surge Success", success_level=1)
        cls.great = CheckOutcomeFactory(name="Surge Great", success_level=2)

    def _band(self, outcome, intensity, control=0, condition=None):
        return SurgeDegreeBandFactory(
            tuning=self.tuning,
            outcome=outcome,
            intensity=intensity,
            control_change=control,
            condition=condition,
        )

    def _engagement(self) -> CharacterEngagement:
        return CharacterEngagement.objects.get(character=self.character.sheet_data)

    def _surge(self, outcome, **kwargs):
        return apply_rolled_surge(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=KIND,
            outcome=outcome,
            potency=14,
            **kwargs,
        )


class BandSelectionTests(SurgeRollTestCase):
    """Kept: pure band selection and its fallbacks are branches no played roll walks."""

    def test_band_fallback_uses_nearest_lower(self) -> None:
        low = self._band(self.fail, 1)
        mid = self._band(self.success, 6)
        self.assertEqual(band_for_outcome(self.tuning, self.partial), low)
        self.assertEqual(band_for_outcome(self.tuning, self.great), mid)

    def test_band_fallback_uses_lowest_when_outcome_is_below_every_band(self) -> None:
        mid = self._band(self.partial, 3)
        self._band(self.success, 6)
        self.assertEqual(band_for_outcome(self.tuning, self.fail), mid)

    def test_no_bands_or_no_outcome_gives_no_band(self) -> None:
        self.assertIsNone(band_for_outcome(self.tuning, self.partial))
        self._band(self.partial, 3)
        self.assertIsNone(band_for_outcome(self.tuning, None))


class QuietNoopTests(SurgeRollTestCase):
    """Kept: each missing-content no-op (no tuning, band, curve, outcome) is authoring state."""

    def test_no_tuning_is_quiet_noop(self) -> None:
        self.tuning.delete()
        with self.assertLogs("world.combat.surge_rolls", level=logging.WARNING):
            beat = self._surge(self.partial)
        self.assertIsNone(beat)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_no_band_is_quiet_noop(self) -> None:
        with self.assertLogs("world.combat.surge_rolls", level=logging.WARNING):
            beat = self._surge(self.partial)
        self.assertIsNone(beat)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_no_curve_is_quiet_noop(self) -> None:
        self._band(self.partial, 3)
        plain = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=plain, status=ParticipantStatus.ACTIVE)
        begin_engagement(participant.character_sheet.character, EngagementType.COMBAT, source=plain)
        beat = apply_rolled_surge(
            encounter=plain,
            participant=participant,
            trigger_kind=KIND,
            outcome=self.partial,
            potency=14,
        )
        self.assertIsNone(beat)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_no_outcome_is_quiet_noop(self) -> None:
        self._band(self.partial, 3)
        self.assertIsNone(self._surge(None))
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)


class RepeatAndDedupTests(SurgeRollTestCase):
    """Kept: the dedup key (round, subject) and the stored roll, called directly."""

    def test_same_round_same_subject_once(self) -> None:
        self._band(self.partial, 3)
        subject = CharacterSheetFactory()
        self.assertIsNotNone(self._surge(self.partial, subject_sheet=subject))
        self.assertIsNone(self._surge(self.partial, subject_sheet=subject))
        self.assertEqual(self._engagement().intensity_modifier, 3)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 1)

    def test_same_round_other_subject_surges(self) -> None:
        self._band(self.partial, 3)
        self.assertIsNotNone(self._surge(self.partial, subject_sheet=CharacterSheetFactory()))
        self.assertIsNotNone(self._surge(self.partial, subject_sheet=CharacterSheetFactory()))
        self.assertEqual(self._engagement().intensity_modifier, 6)

    def test_record_keeps_the_roll(self) -> None:
        self._band(self.partial, 3, control=2)
        self._surge(self.partial)
        record = DramaticSurgeRecord.objects.get()
        self.assertEqual(
            (record.outcome, record.potency, record.control_change, record.amount),
            (self.partial, 14, 2, 3),
        )


class EffectTests(SurgeRollTestCase):
    """Kept: rounding, source attribution and the error paths need a patched collaborator."""

    def test_control_change_lowers_engagement_control(self) -> None:
        self._band(self.fail, 0, control=-2)
        before = self._engagement().control_modifier
        beat = self._surge(self.fail)
        self.assertEqual(self._engagement().control_modifier, before - 2)
        self.assertEqual(beat.control_change, -2)
        self.assertEqual(self._engagement().intensity_modifier, 0)
        self.assertEqual(DramaticSurgeRecord.objects.get().amount, 0)

    def test_condition_band_applies_condition_with_source(self) -> None:
        goaded = ConditionTemplateFactory(name="Surge Goaded")
        taunter = CombatParticipantFactory(encounter=self.encounter).character_sheet.character
        self._band(self.fail, 0, condition=goaded)
        beat = self._surge(self.fail, source_character=taunter)
        instance = ConditionInstance.objects.get(target=self.character, condition=goaded)
        self.assertEqual(instance.source_character, taunter)
        self.assertEqual(instance.source_description, "Surge roll")
        self.assertEqual(beat.condition_name, "Surge Goaded")
        self.assertEqual(DramaticSurgeRecord.objects.get().condition, goaded)

    def test_condition_not_applied_when_surge_deduped(self) -> None:
        goaded = ConditionTemplateFactory(name="Surge Goaded Once")
        self._band(self.fail, 0, condition=goaded)
        self._surge(self.fail)
        ConditionInstance.objects.filter(target=self.character).delete()
        self.assertIsNone(self._surge(self.fail))
        self.assertFalse(ConditionInstance.objects.filter(target=self.character).exists())

    def test_scale_rounds_intensity(self) -> None:
        self._band(self.partial, 10)
        beat = self._surge(self.partial, intensity_scale=0.37)
        self.assertEqual(beat.amount, 4)
        self.assertEqual(self._engagement().intensity_modifier, 4)

    def test_scale_rounds_ties_up(self) -> None:
        for intensity, expected in ((1, 1), (3, 2), (5, 3), (7, 4)):
            with self.subTest(intensity=intensity):
                DramaticSurgeRecord.objects.all().delete()
                self.tuning.bands.all().delete()
                self._band(self.partial, intensity)
                beat = self._surge(self.partial, intensity_scale=0.5)
                self.assertEqual(beat.amount, expected)

    def test_resisted_condition_is_not_claimed(self) -> None:
        goaded = ConditionTemplateFactory(name="Surge Goaded Resisted")
        self._band(self.fail, 2, condition=goaded)
        refused = ApplyConditionResult(success=False, instance=None, message="resisted")
        with (
            patch("world.conditions.services.apply_condition", return_value=refused),
            patch.object(self.character, "msg") as own_msg,
            self.captureOnCommitCallbacks(execute=True),
        ):
            beat = self._surge(self.fail)
        self.assertEqual(beat.condition_name, "")
        self.assertIsNone(DramaticSurgeRecord.objects.get().condition)
        self.assertNotIn("Goaded", own_msg.call_args.args[0])
        self.assertEqual(self._engagement().intensity_modifier, 2)

    def test_condition_failure_rolls_the_surge_back(self) -> None:
        goaded = ConditionTemplateFactory(name="Surge Goaded Raises")
        self._band(self.fail, 2, condition=goaded)
        with (
            patch("world.conditions.services.apply_condition", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            self._surge(self.fail)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)


class RollLineDeliveryTests(SurgeRollTestCase):
    """Kept: a journey cannot open a round's transaction to see the line deferred or dropped."""

    def test_roll_line_waits_for_the_surrounding_transaction_to_commit(self) -> None:
        self._band(self.partial, 3)
        with (
            patch.object(self.character, "msg") as own_msg,
            self.captureOnCommitCallbacks(execute=False) as callbacks,
        ):
            self._surge(self.partial)
            own_msg.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        with patch.object(self.character, "msg") as own_msg:
            callbacks[0]()
        own_msg.assert_called_once()

    def test_a_rolled_back_surge_sends_no_roll_line(self) -> None:
        self._band(self.partial, 3)
        failure = RuntimeError("the round failed")
        with (
            patch.object(self.character, "msg") as own_msg,
            self.captureOnCommitCallbacks(execute=True),
            self.assertRaises(RuntimeError),
            transaction.atomic(),
        ):
            self._surge(self.partial)
            raise failure
        own_msg.assert_not_called()


class ZeroAmountTests(SurgeRollTestCase):
    """A surge that adds no intensity, control or condition writes nothing (#4737).

    Kept: a zero amount needs a scale or band no authored journey sets up.
    """

    def test_zero_amount_with_nothing_else_writes_nothing_and_keeps_the_slot_free(self) -> None:
        self._band(self.partial, 3)
        with patch.object(self.encounter.room, "msg_contents") as room_msg:
            self.assertIsNone(self._surge(self.partial, intensity_scale=0.1))
        room_msg.assert_not_called()
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)
        # The slot is still free: a bigger hit the same round can still surge.
        self.assertIsNotNone(self._surge(self.partial, intensity_scale=1.0))
        self.assertEqual(self._engagement().intensity_modifier, 3)

    def test_zero_intensity_band_with_nothing_else_writes_nothing(self) -> None:
        self._band(self.fail, 0)
        self.assertIsNone(self._surge(self.fail))
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_zero_amount_with_a_control_change_writes_but_does_not_announce_a_surge(self) -> None:
        self._band(self.fail, 0, control=-2)
        with patch.object(self.encounter.room, "msg_contents") as room_msg:
            beat = self._surge(self.fail)
        room_msg.assert_not_called()
        self.assertEqual(beat.narration, "")
        self.assertEqual(self._engagement().control_modifier, -2)
        self.assertEqual(DramaticSurgeRecord.objects.get().amount, 0)

    def test_zero_amount_with_a_condition_writes_but_does_not_announce_a_surge(self) -> None:
        goaded = ConditionTemplateFactory(name="Surge Goaded Zero")
        self._band(self.fail, 0, condition=goaded)
        with patch.object(self.encounter.room, "msg_contents") as room_msg:
            beat = self._surge(self.fail)
        room_msg.assert_not_called()
        self.assertEqual(beat.condition_name, "Surge Goaded Zero")

    def test_a_surge_with_intensity_still_announces(self) -> None:
        self._band(self.partial, 3)
        with patch.object(self.encounter.room, "msg_contents") as room_msg:
            self._surge(self.partial)
        room_msg.assert_called_once()


class CauseTests(SurgeRollTestCase):
    def test_the_cause_is_stored_on_the_record_and_never_in_the_room_line(self) -> None:
        self._band(self.partial, 3)
        with patch.object(self.encounter.room, "msg_contents") as room_msg:
            self._surge(self.partial, cause="Mira taunts you.")
        self.assertEqual(DramaticSurgeRecord.objects.get().cause, "Mira taunts you.")
        self.assertNotIn("taunts", room_msg.call_args.args[0])

    def test_a_surge_with_no_cause_stores_an_empty_one(self) -> None:
        self._band(self.partial, 3)
        self._surge(self.partial)
        self.assertEqual(DramaticSurgeRecord.objects.get().cause, "")


class PotencyLabelTests(SurgeRollTestCase):
    """Kept: a new rolled kind without a label would only fail in a journey for that kind."""

    def test_every_rolled_kind_has_a_potency_label(self) -> None:
        self.assertEqual(set(POTENCY_LABELS), set(ROLLED_SURGE_TRIGGER_KINDS))

    def test_roll_line_never_raises_for_an_unlabelled_kind(self) -> None:
        line = roll_line(
            check_type=self.check_type,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
            potency=9,
            outcome=self.partial,
            amount=2,
            control_change=0,
            condition_name="",
        )
        self.assertIn("vs difficulty 9", line)


class RollLineFormatTests(SurgeRollTestCase):
    def _line(self, **overrides) -> str:
        fields = {
            "check_type": self.check_type,
            "trigger_kind": SurgeTriggerKind.TAUNT_RECEIVED,
            "potency": 60,
            "outcome": self.fail,
            "amount": 2,
            "control_change": 0,
            "condition_name": "",
        }
        fields.update(overrides)
        return roll_line(**fields)

    def test_parts_are_joined_with_a_middle_dot_and_unchanged_control_is_left_out(self) -> None:
        self.assertEqual(
            self._line(outcome=self.partial, amount=3),
            "Surge Composure check vs taunt potency 60 · Surge Partial · Intensity +3",
        )

    def test_changed_control_then_the_condition_come_last(self) -> None:
        self.assertEqual(
            self._line(control_change=-1, condition_name="Goaded"),
            "Surge Composure check vs taunt potency 60 · Surge Failure · Intensity +2 "
            "· control -1 · Goaded",
        )

    def test_a_hurt_ally_surge_names_the_bond_difficulty_and_the_wound_scaling(self) -> None:
        self.assertEqual(
            self._line(trigger_kind=SurgeTriggerKind.ALLY_HURT, potency=15, outcome=self.success),
            "Surge Composure check vs bond difficulty 15 · Surge Success "
            "· Intensity +2 (scaled by the wound)",
        )

    def test_a_rally_keeps_its_rally_difficulty_label(self) -> None:
        self.assertIn(
            "vs rally difficulty 10", self._line(trigger_kind=SurgeTriggerKind.RALLIED, potency=10)
        )


class RolledSurgePossibleTests(SurgeRollTestCase):
    """Kept: the pre-roll predicate has four branches, two of them dedup state."""

    def test_possible_with_an_engagement_and_no_record(self) -> None:
        self.assertTrue(rolled_surge_possible(self.encounter, self.participant, KIND, None))

    def test_not_possible_once_the_round_has_a_record_for_the_subject(self) -> None:
        subject = CharacterSheetFactory()
        self._band(self.partial, 3)
        self._surge(self.partial, subject_sheet=subject)
        self.assertFalse(rolled_surge_possible(self.encounter, self.participant, KIND, subject))
        self.assertTrue(
            rolled_surge_possible(self.encounter, self.participant, KIND, CharacterSheetFactory())
        )

    def test_possible_again_next_round(self) -> None:
        self._band(self.partial, 3)
        self._surge(self.partial)
        self.encounter.round_number += 1
        self.assertTrue(rolled_surge_possible(self.encounter, self.participant, KIND, None))

    def test_not_possible_without_a_combat_engagement(self) -> None:
        CharacterEngagement.objects.filter(character=self.character.sheet_data).delete()
        self.assertFalse(rolled_surge_possible(self.encounter, self.participant, KIND, None))

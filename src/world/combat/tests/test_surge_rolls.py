"""The surge-roll core service (#4737): bands, dedup, control, conditions, roll line."""

from itertools import pairwise
import logging
from unittest.mock import patch

from django.test import TestCase, override_settings

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.surge_rolls import (
    apply_rolled_surge,
    band_for_outcome,
    surge_roll_for_participant,
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
    def test_better_outcome_never_surges_less(self) -> None:
        self._band(self.fail, 1)
        self._band(self.partial, 3)
        self._band(self.success, 6)
        amounts = []
        for outcome in (self.fail, self.partial, self.success):
            DramaticSurgeRecord.objects.all().delete()
            before = self._engagement().intensity_modifier
            beat = self._surge(outcome)
            self.assertIsNotNone(beat)
            amounts.append(beat.amount)
            self.assertEqual(self._engagement().intensity_modifier - before, beat.amount)
        for worse, better in pairwise(amounts):
            self.assertGreaterEqual(better, worse)

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
    def test_second_round_surges_again(self) -> None:
        self._band(self.partial, 3)
        self.assertIsNotNone(self._surge(self.partial))
        self.encounter.round_number += 1
        self.encounter.save(update_fields=["round_number"])
        self.assertIsNotNone(self._surge(self.partial))
        self.assertEqual(self._engagement().intensity_modifier, 6)
        rounds = set(DramaticSurgeRecord.objects.values_list("repeat_round", flat=True))
        self.assertEqual(rounds, {self.encounter.round_number - 1, self.encounter.round_number})

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


class NarrationTests(SurgeRollTestCase):
    def test_roll_line_goes_to_participant_only_and_room_gets_generic_narration(self) -> None:
        goaded = ConditionTemplateFactory(name="Surge Goaded Line")
        self._band(self.partial, 5, condition=goaded)
        bystander = CombatParticipantFactory(encounter=self.encounter).character_sheet.character
        with (
            patch.object(self.character, "msg") as own_msg,
            patch.object(bystander, "msg") as other_msg,
            patch.object(self.encounter.room, "msg_contents") as room_msg,
        ):
            self._surge(self.partial)
        own_msg.assert_called_once_with(
            "Surge Composure check vs taunt potency 14. Surge Partial. "
            "Intensity +5, control 0. Surge Goaded Line."
        )
        other_msg.assert_not_called()
        room_msg.assert_called_once()
        generic = room_msg.call_args.args[0]
        self.assertEqual(generic, f"{self.character.db_key} surges.")
        for secret in ("Surge Composure", "potency", "Partial", "Goaded"):
            self.assertNotIn(secret, generic)


class RollTests(SurgeRollTestCase):
    def test_surge_roll_goes_through_the_social_check_seam(self) -> None:
        forced = CheckResult(
            check_type=self.check_type,
            outcome=self.success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        with patch("world.checks.services.perform_check", return_value=forced) as rolled:
            result = surge_roll_for_participant(self.participant, self.check_type, 14)
        self.assertIs(result, forced)
        self.assertEqual(rolled.call_args.kwargs["target_difficulty"], 14)
        self.assertEqual(rolled.call_args.args[:2], (self.character, self.check_type))

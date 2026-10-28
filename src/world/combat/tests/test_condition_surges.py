"""Emotional conditions feed intensity each round (#4739).

The journey ``AngerFeedsHerIntensity`` plays the round opening over telnet and the web.
What stays here: the edges a journey does not reach cheaply (two conditions summed into one
record, suppressed and resolved instances, a zero sum, an NPC opponent, the one-query read,
the line held until commit).
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from world.combat.condition_surges import (
    apply_condition_intensity_surges,
    condition_fed_line,
    condition_feeds_intensity,
    condition_intensity_by_target,
)
from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.services import begin_declaration_phase
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.scenes.constants import RoundStatus


@override_settings(SEED_SAMPLE_CONTENT=True)  # EscalationCurveFactory gates on #2698
class ConditionIntensitySurgeTests(TestCase):
    def setUp(self) -> None:
        self.curve = EscalationCurveFactory(start_round=50)
        self.encounter = CombatEncounterFactory(
            escalation_curve=self.curve, round_number=1, status=RoundStatus.DECLARING
        )
        self.seat = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.character = self.seat.character_sheet.character
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)

    def _feeding(self, name: str, per_round: int, target=None, **instance_kwargs):
        template = ConditionTemplateFactory(name=name, has_progression=True)
        stage = ConditionStageFactory(
            condition=template, stage_order=1, intensity_per_round=per_round
        )
        return ConditionInstanceFactory(
            target=target or self.character,
            condition=template,
            current_stage=stage,
            **instance_kwargs,
        )

    def _intensity(self) -> int:
        engagement = CharacterEngagement.objects.get(character=self.seat.character_sheet)
        return engagement.intensity_modifier

    def _records(self):
        return DramaticSurgeRecord.objects.filter(trigger_kind=SurgeTriggerKind.CONDITION_FED)

    def _feed(self):
        with self.captureOnCommitCallbacks(execute=True):
            return apply_condition_intensity_surges(self.encounter)

    def test_two_conditions_sum_into_one_record(self) -> None:
        self._feeding("Unit Anger", 2)
        self._feeding("Unit Grief", 1)

        beats = self._feed()

        self.assertEqual(len(beats), 1)
        record = self._records().get()
        self.assertEqual(record.amount, 3)
        self.assertEqual(record.repeat_round, 1)
        self.assertIsNone(record.outcome)
        self.assertEqual(record.participant, self.seat)
        self.assertEqual(record.cause, condition_fed_line(["Unit Anger", "Unit Grief"], 3))
        self.assertEqual(self._intensity(), 3)

    def test_once_per_round_and_again_next_round(self) -> None:
        self._feeding("Unit Fury", 2)
        self._feed()
        self._feed()
        self.assertEqual(self._records().count(), 1)
        self.assertEqual(self._intensity(), 2)

        self.encounter.round_number = 2
        self.encounter.save(update_fields=["round_number"])
        self._feed()
        self.assertEqual(self._records().count(), 2)
        self.assertEqual(self._intensity(), 4)

    def test_no_curve_no_surge(self) -> None:
        self._feeding("Unit Rage", 2)
        self.encounter.escalation_curve = None
        self.encounter.save(update_fields=["escalation_curve"])

        self.assertEqual(self._feed(), [])
        self.assertFalse(self._records().exists())

    def test_suppressed_and_resolved_instances_do_not_feed(self) -> None:
        self._feeding("Unit Suppressed", 2, is_suppressed=True)
        self._feeding("Unit Resolved", 3, resolved_at=timezone.now())

        self.assertEqual(self._feed(), [])
        self.assertFalse(self._records().exists())

    def test_a_zero_sum_writes_nothing(self) -> None:
        self._feeding("Unit Calm", 0)

        self.assertEqual(self._feed(), [])
        self.assertFalse(self._records().exists())

    def test_an_npc_opponent_never_surges(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter)
        self._feeding("Unit Opponent Anger", 2, target=opponent.objectdb)

        self.assertEqual(self._feed(), [])
        self.assertFalse(DramaticSurgeRecord.objects.exists())

    def test_the_line_waits_for_commit(self) -> None:
        self._feeding("Unit Spite", 2)
        with patch.object(type(self.character), "msg") as msg:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                apply_condition_intensity_surges(self.encounter)
            msg.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
        msg.assert_called_once_with("Unit Spite · Intensity +2")

    def test_one_query_reads_every_character(self) -> None:
        other = CombatParticipantFactory(encounter=self.encounter, status=ParticipantStatus.ACTIVE)
        self._feeding("Unit One", 1)
        self._feeding("Unit Two", 2, target=other.character_sheet.character)
        ids = [self.character.pk, other.character_sheet.character_id]
        with self.assertNumQueries(1):
            fed = condition_intensity_by_target(ids)
        self.assertEqual(fed[self.character.pk], (1, ["Unit One"]))
        self.assertEqual(fed[other.character_sheet.character_id], (2, ["Unit Two"]))

    def test_condition_feeds_intensity_reads_any_stage(self) -> None:
        anger = ConditionTemplateFactory(name="Unit Staged Anger", has_progression=True)
        ConditionStageFactory(condition=anger, stage_order=1, intensity_per_round=0)
        ConditionStageFactory(condition=anger, stage_order=2, intensity_per_round=1)
        plain = ConditionTemplateFactory(name="Unit Plain")
        self.assertEqual(condition_feeds_intensity([anger.pk, plain.pk, None]), {anger.pk})


@override_settings(SEED_SAMPLE_CONTENT=True)  # EscalationCurveFactory gates on #2698
class RoundOpeningRollbackTests(TestCase):
    """A round opening that raises after the feed leaves the cached rows as stored."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            escalation_curve=EscalationCurveFactory(start_round=50),
            round_number=1,
            status=RoundStatus.BETWEEN_ROUNDS,
        )
        CombatOpponentFactory(encounter=self.encounter)
        self.seat = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.character = self.seat.character_sheet.character
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)
        template = ConditionTemplateFactory(name="Rollback Anger", has_progression=True)
        stage = ConditionStageFactory(condition=template, stage_order=1, intensity_per_round=2)
        ConditionInstanceFactory(target=self.character, condition=template, current_stage=stage)

    def test_a_raise_after_the_feed_restores_the_cached_engagement(self) -> None:
        engagement = CharacterEngagement.objects.get(character=self.seat.character_sheet)
        fed_in_memory: list[int] = []

        def feed_then_note(encounter):
            beats = apply_condition_intensity_surges(encounter)
            fed_in_memory.append(engagement.intensity_modifier)
            return beats

        with (
            patch(
                "world.combat.services.declarations.declaration_phase._dissolve_graduated_bonds",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "world.combat.condition_surges.apply_condition_intensity_surges",
                side_effect=feed_then_note,
            ),
            self.assertRaises(RuntimeError),
        ):
            begin_declaration_phase(self.encounter)

        # The feed did raise the cached engagement before the round opening failed.
        self.assertEqual(fed_in_memory, [2])
        stored = CharacterEngagement.objects.filter(pk=engagement.pk).values_list(
            "intensity_modifier", "control_modifier"
        )
        self.assertEqual((engagement.intensity_modifier, engagement.control_modifier), stored.get())
        self.assertEqual(engagement.intensity_modifier, 0)
        self.assertIs(
            CharacterEngagement.objects.get(character=self.seat.character_sheet), engagement
        )
        self.assertFalse(DramaticSurgeRecord.objects.exists())
        self.assertEqual(list(DramaticSurgeRecord.get_all_cached_instances()), [])
        self.assertEqual(self.encounter.round_number, 1)
        self.assertEqual(self.encounter.status, RoundStatus.BETWEEN_ROUNDS)

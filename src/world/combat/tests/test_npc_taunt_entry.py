"""An NPC taunt entry supplies a potency the targeted player character rolls against (#4737)."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import CombatParticipant, DramaticSurgeRecord
from world.combat.services import _resolve_npc_action
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import CharacterVitals


@override_settings(SEED_SAMPLE_CONTENT=True)  # EscalationCurveFactory gates on #2698
class NpcTauntEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.curve = EscalationCurveFactory(surge_narration="{character} surges.")
        cls.encounter = CombatEncounterFactory(escalation_curve=cls.curve, round_number=1)
        cls.target = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        cls.character = cls.target.character_sheet.character
        CharacterVitalsFactory(character_sheet=cls.target.character_sheet)
        begin_engagement(cls.character, EngagementType.COMBAT, source=cls.encounter)
        cls.opponent = CombatOpponentFactory(encounter=cls.encounter)
        cls.tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED,
            check_type=CheckTypeFactory(name="Npc Taunt Composure"),
        )
        cls.partial = CheckOutcomeFactory(name="Npc Taunt Partial", success_level=0)
        cls.success = CheckOutcomeFactory(name="Npc Taunt Success", success_level=1)
        SurgeDegreeBandFactory(tuning=cls.tuning, outcome=cls.partial, intensity=3)
        SurgeDegreeBandFactory(tuning=cls.tuning, outcome=cls.success, intensity=6)

    def _taunt_action(self, **entry_kwargs):
        entry = ThreatPoolEntryFactory(base_damage=0, taunt_potency=14, **entry_kwargs)
        action = CombatOpponentActionFactory(
            opponent=self.opponent, threat_entry=entry, round_number=1
        )
        action.targets.add(self.target)
        return action

    def _resolve(self, action, outcome):
        with (
            force_check_outcome(outcome),
            patch("world.combat.interaction_services.broadcast_action_outcome") as broadcast,
        ):
            result = _resolve_npc_action(self.opponent, action, None, None)
        return result, broadcast

    def _intensity(self) -> int:
        engagement = CharacterEngagement.objects.get(character=self.target.character_sheet)
        return engagement.intensity_modifier

    def test_npc_taunt_entry_does_no_damage_and_surges_pc(self) -> None:
        action = self._taunt_action()
        health_before = CharacterVitals.objects.filter(
            character_sheet=self.target.character_sheet
        ).values_list("health", flat=True)
        health_before = list(health_before)
        result, _ = self._resolve(action, self.partial)

        self.assertEqual(result.damage_results, [])
        self.assertEqual(result.damage_consequences, [])
        health_after = list(
            CharacterVitals.objects.filter(character_sheet=self.target.character_sheet).values_list(
                "health", flat=True
            )
        )
        self.assertEqual(health_after, health_before)
        record = DramaticSurgeRecord.objects.get()
        self.assertEqual(record.participant, self.target)
        self.assertEqual(record.trigger_kind, SurgeTriggerKind.TAUNT_RECEIVED)
        self.assertEqual(record.potency, 14)
        self.assertEqual(record.outcome, self.partial)
        self.assertIsNone(record.subject_sheet)
        self.assertEqual(self._intensity(), 3)

    def test_better_roll_against_npc_taunt_surges_more(self) -> None:
        self._resolve(self._taunt_action(), self.partial)
        low = self._intensity()
        DramaticSurgeRecord.objects.all().delete()
        self._resolve(self._taunt_action(), self.success)
        self.assertGreater(self._intensity() - low, low)

    def test_roll_line_goes_to_the_targeted_character(self) -> None:
        action = self._taunt_action()
        live = CombatParticipant.objects.get(pk=self.target.pk)  # the idmapper's instance
        with (
            patch.object(live.character_sheet.character, "msg") as own_msg,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self._resolve(action, self.partial)
        self.assertIn(
            "Npc Taunt Composure check vs taunt potency 14. Npc Taunt Partial.",
            own_msg.call_args.args[0],
        )

    def test_a_second_taunt_on_the_same_pc_in_a_round_rolls_nothing_and_prints_nothing(
        self,
    ) -> None:
        self._resolve(self._taunt_action(), self.partial)
        live = CombatParticipant.objects.get(pk=self.target.pk)
        with (
            patch("world.combat.surge_rolls.surge_roll_for_participant") as roll,
            patch.object(live.character_sheet.character, "msg") as own_msg,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self._resolve(self._taunt_action(), self.partial)
        roll.assert_not_called()
        own_msg.assert_not_called()
        self.assertEqual(DramaticSurgeRecord.objects.count(), 1)
        self.assertEqual(self._intensity(), 3)

    def test_a_target_with_no_combat_engagement_is_not_rolled_for(self) -> None:
        CharacterEngagement.objects.filter(character=self.target.character_sheet).delete()
        with patch("world.combat.surge_rolls.surge_roll_for_participant") as roll:
            self._resolve(self._taunt_action(), self.partial)
        roll.assert_not_called()

    def test_a_taunt_entry_aimed_at_an_opponent_is_skipped_entirely(self) -> None:
        victim = CombatOpponentFactory(encounter=self.encounter)
        entry = ThreatPoolEntryFactory(base_damage=0, taunt_potency=14)
        action = CombatOpponentActionFactory(
            opponent=self.opponent, threat_entry=entry, round_number=1
        )
        action.opponent_targets.add(victim)
        result, broadcast = self._resolve(action, self.partial)
        self.assertEqual(result.damage_results, [])
        broadcast.assert_not_called()
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_outcome_line_uses_authored_hit_narration(self) -> None:
        action = self._taunt_action(hit_narration="{actor} sneers at {target}.")
        _, broadcast = self._resolve(action, self.partial)
        narration = broadcast.call_args.kwargs["narration"]
        self.assertTrue(narration.startswith(self.opponent.name))
        self.assertIn("sneers at", narration)
        self.assertNotIn("{", narration)
        self.assertNotIn("misses", narration)

    def test_outcome_line_without_authored_text_is_plain(self) -> None:
        action = self._taunt_action()
        _, broadcast = self._resolve(action, self.partial)
        narration = broadcast.call_args.kwargs["narration"]
        self.assertTrue(narration.startswith(f"{self.opponent.name} taunts "))
        self.assertNotIn("damage", narration)
        self.assertNotIn("misses", narration)

    def test_npc_taunt_without_a_curve_does_nothing(self) -> None:
        plain = CombatEncounterFactory(round_number=1)
        target = CombatParticipantFactory(encounter=plain, status=ParticipantStatus.ACTIVE)
        begin_engagement(target.character_sheet.character, EngagementType.COMBAT, source=plain)
        opponent = CombatOpponentFactory(encounter=plain)
        entry = ThreatPoolEntryFactory(base_damage=0, taunt_potency=14)
        action = CombatOpponentActionFactory(opponent=opponent, threat_entry=entry, round_number=1)
        action.targets.add(target)
        with (
            force_check_outcome(self.partial),
            patch("world.combat.interaction_services.broadcast_action_outcome"),
        ):
            _resolve_npc_action(opponent, action, None, None)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_ordinary_entry_still_deals_damage_and_never_surges(self) -> None:
        entry = ThreatPoolEntryFactory(base_damage=5)
        action = CombatOpponentActionFactory(
            opponent=self.opponent, threat_entry=entry, round_number=1
        )
        action.targets.add(self.target)
        result, _ = self._resolve(action, self.partial)
        self.assertEqual(len(result.damage_results), 1)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

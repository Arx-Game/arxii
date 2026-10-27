"""An NPC taunt entry supplies a potency the targeted player character rolls against (#4737).

The journey ``BeingTauntedByAnNpc`` plays the entry through a real round: no damage, the
record, the roll line, the room's generic line, a better result and an encounter with no
curve. What stays here is what that journey cannot reach: the no-roll edges (a second taunt,
no engagement, an entry aimed at an opponent) and an ordinary entry. The authored hit
text and the plain line are read off the pushed row in that journey.
"""

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

    def test_the_cause_is_the_authored_line_the_room_gets_or_a_plain_one(self) -> None:
        name = self.character.key
        self._resolve(self._taunt_action(hit_narration="{actor} sneers at {target}."), self.partial)
        self.assertEqual(
            DramaticSurgeRecord.objects.get().cause, f"{self.opponent.name} sneers at {name}."
        )

        DramaticSurgeRecord.objects.all().delete()
        self._resolve(self._taunt_action(), self.partial)
        self.assertEqual(
            DramaticSurgeRecord.objects.get().cause, f"{self.opponent.name} taunts {name}."
        )

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

    def test_ordinary_entry_still_deals_damage_and_never_surges(self) -> None:
        entry = ThreatPoolEntryFactory(base_damage=5)
        action = CombatOpponentActionFactory(
            opponent=self.opponent, threat_entry=entry, round_number=1
        )
        action.targets.add(self.target)
        result, _ = self._resolve(action, self.partial)
        self.assertEqual(len(result.damage_results), 1)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

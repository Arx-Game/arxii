"""A player character taunts another player character (#4737): a roll, then a rolled surge.

The journey ``BeingTauntedByAnotherPlayer`` types ``combat taunt Tomas`` and plays the round:
the potency from the taunter's real rating, the record, the roll line, a better result and
the next round. The declaration's error mapping and the resolution's no-op edges stay here.
"""

from contextlib import ExitStack
from unittest.mock import patch

from django.test import TestCase, override_settings

from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import CombatManeuver, ParticipantStatus, SurgeTriggerKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
    ThreatPoolFactory,
)
from world.combat.models import DramaticSurgeRecord, ThreatRecord
from world.combat.services import _resolve_taunt, declare_taunt
from world.combat.social_combat_content import ensure_social_combat_content
from world.combat.surge_rolls import surge_roll_for_participant
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals

TAUNT_MODULE = "world.combat.services.declarations.taunt"


@override_settings(SEED_SAMPLE_CONTENT=True)  # curve factory and social content gate on #2698
class PlayerTauntTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_social_combat_content()
        cls.curve = EscalationCurveFactory(surge_narration="{character} surges.")
        cls.encounter = CombatEncounterFactory(
            escalation_curve=cls.curve, round_number=1, status=RoundStatus.DECLARING
        )
        cls.taunter = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        cls.target = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        cls.target_character = cls.target.character_sheet.character
        begin_engagement(cls.target_character, EngagementType.COMBAT, source=cls.encounter)
        cls.composure = CheckTypeFactory(name="Taunt Composure")
        cls.tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED, check_type=cls.composure
        )
        cls.fail = CheckOutcomeFactory(name="Taunt Failure", success_level=-1)
        cls.partial = CheckOutcomeFactory(name="Taunt Partial", success_level=0)
        cls.success = CheckOutcomeFactory(name="Taunt Success", success_level=1)
        for outcome, intensity in ((cls.fail, 1), (cls.partial, 3), (cls.success, 6)):
            SurgeDegreeBandFactory(tuning=cls.tuning, outcome=outcome, intensity=intensity)

    def _kill_target(self) -> None:
        CharacterVitals.objects.update_or_create(
            character_sheet=self.target.character_sheet,
            defaults={"life_state": CharacterLifeState.DEAD},
        )

    def _intensity(self) -> int:
        engagement = CharacterEngagement.objects.get(character=self.target.character_sheet)
        return engagement.intensity_modifier

    def _taunt(self, target_outcome, rating: int = 12, taunter=None, target=None) -> list:
        """Declare and resolve a taunt, forcing the target's roll.

        The taunter's check rating is pinned to ``rating`` (nothing is rolled for the
        taunter). Returns the (check type, difficulty) of every roll the target made.
        """
        taunter = taunter or self.taunter
        target = target or self.target
        action = declare_taunt(taunter, target)
        target_rolls: list = []

        def target_roll(participant, check_type, potency):
            target_rolls.append((check_type, potency))
            with force_check_outcome(target_outcome):
                return surge_roll_for_participant(participant, check_type, potency)

        with ExitStack() as stack:
            stack.enter_context(
                patch("world.checks.services.compute_check_rating", return_value=rating)
            )
            stack.enter_context(
                patch(f"{TAUNT_MODULE}.surge_roll_for_participant", side_effect=target_roll)
            )
            _resolve_taunt(taunter, action)
        return target_rolls


class DeclareTests(PlayerTauntTestCase):
    """Kept: the declaration's error mapping is a parser with branches, not a played story."""

    def test_participant_target_is_stored_as_ally_target(self) -> None:
        action = declare_taunt(self.taunter, self.target)
        self.assertEqual(action.maneuver, CombatManeuver.TAUNT)
        self.assertEqual(action.focused_ally_target, self.target)
        self.assertIsNone(action.focused_opponent_target)
        self.assertTrue(action.is_ready)

    def test_taunt_declare_rejects_self_and_dead(self) -> None:
        with self.assertRaisesMessage(ValueError, "yourself"):
            declare_taunt(self.taunter, self.taunter)
        self._kill_target()
        with self.assertRaisesMessage(ValueError, "dead"):
            declare_taunt(self.taunter, self.target)

    def test_declare_rejects_inactive_and_other_encounter_targets(self) -> None:
        gone = CombatParticipantFactory(encounter=self.encounter, status=ParticipantStatus.FLED)
        with self.assertRaisesMessage(ValueError, "active participant"):
            declare_taunt(self.taunter, gone)
        elsewhere = CombatParticipantFactory(status=ParticipantStatus.ACTIVE)
        with self.assertRaisesMessage(ValueError, "active participant"):
            declare_taunt(self.taunter, elsewhere)

    def test_declaring_an_opponent_taunt_clears_an_earlier_participant_target(self) -> None:
        declare_taunt(self.taunter, self.target)
        opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=ThreatPoolFactory())
        action = declare_taunt(self.taunter, opponent)
        self.assertEqual(action.focused_opponent_target, opponent)
        self.assertIsNone(action.focused_ally_target)


class ResolveTests(PlayerTauntTestCase):
    """Kept: clamps, dedup and quiet no-ops need a pinned rating, a removed row or a status flip."""

    def test_the_cause_names_the_taunter(self) -> None:
        self._taunt(self.partial)
        self.assertEqual(
            DramaticSurgeRecord.objects.get().cause,
            f"{self.taunter.character_sheet.character.key} taunts you.",
        )

    def test_a_negative_rating_is_a_potency_of_zero(self) -> None:
        self._taunt(self.partial, rating=-4)
        self.assertEqual(DramaticSurgeRecord.objects.get().potency, 0)

    def test_a_second_taunt_on_the_same_target_rolls_nothing(self) -> None:
        self._taunt(self.partial)
        again = self._taunt(self.partial)
        self.assertEqual(again, [])
        self.assertEqual(DramaticSurgeRecord.objects.count(), 1)

    def test_a_target_with_no_combat_engagement_rolls_nothing(self) -> None:
        CharacterEngagement.objects.filter(character=self.target.character_sheet).delete()
        self.assertEqual(self._taunt(self.partial), [])
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_taunt_on_npc_unchanged_threat_only(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=ThreatPoolFactory())
        action = declare_taunt(self.taunter, opponent)
        with force_check_outcome(self.success):
            _resolve_taunt(self.taunter, action)
        self.assertTrue(
            ThreatRecord.objects.filter(
                encounter=self.encounter, opponent=opponent, participant=self.taunter
            ).exists()
        )
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)
        self.assertEqual(self._intensity(), 0)

    def test_target_who_left_between_declaration_and_resolution_is_a_noop(self) -> None:
        action = declare_taunt(self.taunter, self.target)
        self.target.status = ParticipantStatus.FLED
        self.target.save(update_fields=["status"])
        with force_check_outcome(self.success):
            _resolve_taunt(self.taunter, action)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_target_who_died_between_declaration_and_resolution_is_a_noop(self) -> None:
        action = declare_taunt(self.taunter, self.target)
        self._kill_target()
        with force_check_outcome(self.success):
            _resolve_taunt(self.taunter, action)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_no_tuning_is_a_noop(self) -> None:
        self.tuning.delete()
        action = declare_taunt(self.taunter, self.target)
        with (
            force_check_outcome(self.success),
            self.assertLogs("world.combat.surge_rolls", level="WARNING"),
        ):
            _resolve_taunt(self.taunter, action)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

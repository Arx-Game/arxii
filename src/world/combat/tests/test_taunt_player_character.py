"""A player character taunts another player character (#4737): a roll, then a rolled surge."""

from contextlib import ExitStack
from unittest.mock import patch

from django.test import TestCase, override_settings

from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
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
from world.combat.services.declarations.social_check import roll_social_check
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

    def _taunt(self, target_outcome, taunter=None, target=None) -> list[CheckResult]:
        """Declare and resolve a taunt, forcing the taunter's roll and then the target's.

        Returns the taunter's roll so a test can read its points.
        """
        taunter = taunter or self.taunter
        target = target or self.target
        action = declare_taunt(taunter, target)
        taunter_rolls: list[CheckResult] = []

        def taunter_roll(*args, **kwargs) -> CheckResult:
            result = roll_social_check(*args, **kwargs)
            taunter_rolls.append(result)
            return result

        def target_roll(*args, **kwargs) -> CheckResult:
            with force_check_outcome(target_outcome):
                return surge_roll_for_participant(*args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(
                patch(f"{TAUNT_MODULE}.roll_social_check", side_effect=taunter_roll)
            )
            stack.enter_context(
                patch(f"{TAUNT_MODULE}.surge_roll_for_participant", side_effect=target_roll)
            )
            stack.enter_context(force_check_outcome(self.success))
            _resolve_taunt(taunter, action)
        return taunter_rolls


class DeclareTests(PlayerTauntTestCase):
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
    def test_pc_taunts_pc_actor_result_is_target_potency(self) -> None:
        taunter_rolls = self._taunt(self.partial)
        self.assertEqual(len(taunter_rolls), 1)
        record = DramaticSurgeRecord.objects.get()
        self.assertEqual(record.potency, taunter_rolls[0].total_points)
        self.assertEqual(record.trigger_kind, SurgeTriggerKind.TAUNT_RECEIVED)

    def test_pc_taunt_surges_target_and_records_roll(self) -> None:
        with patch.object(self.target_character, "msg") as own_msg:
            self._taunt(self.partial)
        record = DramaticSurgeRecord.objects.get()
        self.assertEqual(record.participant, self.target)
        self.assertEqual(record.subject_sheet, self.taunter.character_sheet)
        self.assertEqual(record.outcome, self.partial)
        self.assertEqual(record.amount, 3)
        self.assertEqual(self._intensity(), 3)
        line = own_msg.call_args.args[0]
        self.assertIn("Taunt Composure check vs taunt potency", line)
        self.assertIn("Taunt Partial", line)

    def test_better_composure_surges_more(self) -> None:
        amounts = []
        for outcome in (self.fail, self.partial, self.success):
            DramaticSurgeRecord.objects.all().delete()
            before = self._intensity()
            self._taunt(outcome)
            amounts.append(self._intensity() - before)
        self.assertEqual(amounts, sorted(amounts))
        self.assertGreater(amounts[-1], amounts[0])

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

    def test_second_round_taunt_surges_again_and_same_round_once(self) -> None:
        self._taunt(self.partial)
        self._taunt(self.partial)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 1)
        self.encounter.round_number = 2
        self.encounter.save(update_fields=["round_number"])
        self._taunt(self.partial)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 2)
        self.assertEqual(self._intensity(), 6)

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

    def test_no_escalation_curve_is_a_noop(self) -> None:
        plain = CombatEncounterFactory(round_number=1, status=RoundStatus.DECLARING)
        taunter = CombatParticipantFactory(encounter=plain, status=ParticipantStatus.ACTIVE)
        target = CombatParticipantFactory(encounter=plain, status=ParticipantStatus.ACTIVE)
        begin_engagement(target.character_sheet.character, EngagementType.COMBAT, source=plain)
        action = declare_taunt(taunter, target)
        with force_check_outcome(self.success):
            _resolve_taunt(taunter, action)
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

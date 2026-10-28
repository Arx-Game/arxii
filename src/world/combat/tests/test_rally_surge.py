"""Rally raises the rallied ally's intensity through a rolled surge (#4737).

The journey ``BeingRallied`` types ``combat rally`` and plays the round (the roll line, the
record, Inspired, the next round). What stays here: the tuned check (no name fallback,
#4739), degrees across every band, a failed rally, and the missing-tuning and no-curve edges.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings

from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import RALLY_BASE_DIFFICULTY, ParticipantStatus, SurgeTriggerKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.services import _resolve_rally, declare_rally
from world.combat.social_combat_content import (
    INSPIRED_SEED_TEMPLATE_NAME,
    ensure_social_combat_content,
)
from world.conditions.models import ConditionInstance
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory


@override_settings(SEED_SAMPLE_CONTENT=True)  # curve factory and social content gate on #2698
class RallySurgeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_social_combat_content()
        cls.curve = EscalationCurveFactory(surge_narration="{character} surges.")
        cls.encounter = CombatEncounterFactory(
            escalation_curve=cls.curve, round_number=1, status=RoundStatus.DECLARING
        )
        cls.rallier = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        cls.ally = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        begin_engagement(
            cls.ally.character_sheet.character, EngagementType.COMBAT, source=cls.encounter
        )
        cls.tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.RALLIED, check_type=CheckTypeFactory(name="Rally Surge")
        )
        cls.fail = CheckOutcomeFactory(name="Rally Failure", success_level=-1)
        cls.partial = CheckOutcomeFactory(name="Rally Partial", success_level=0)
        cls.success = CheckOutcomeFactory(name="Rally Success", success_level=1)
        cls.great = CheckOutcomeFactory(name="Rally Great", success_level=2)
        for outcome, intensity in (
            (cls.fail, 1),
            (cls.partial, 2),
            (cls.success, 5),
            (cls.great, 8),
        ):
            SurgeDegreeBandFactory(tuning=cls.tuning, outcome=outcome, intensity=intensity)

    def _intensity(self) -> int:
        engagement = CharacterEngagement.objects.get(character=self.ally.character_sheet)
        return engagement.intensity_modifier

    def _rally(self, outcome) -> None:
        action = declare_rally(self.rallier, self.ally)
        with force_check_outcome(outcome):
            _resolve_rally(self.rallier, action)

    def test_the_cause_names_the_rallier(self) -> None:
        self._rally(self.success)
        self.assertEqual(
            DramaticSurgeRecord.objects.get().cause,
            f"{self.rallier.character_sheet.character.key} rallies "
            f"{self.ally.character_sheet.character.key}.",
        )

    def test_rally_rolls_the_tuned_check_at_the_fixed_difficulty(self) -> None:
        action = declare_rally(self.rallier, self.ally)
        with (
            patch.object(self.ally.character_sheet.character, "msg") as ally_msg,
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(self.success) as capture,
        ):
            _resolve_rally(self.rallier, action)
        self.assertEqual(capture.check_type, self.tuning.check_type)
        self.assertEqual(capture.target_difficulty, RALLY_BASE_DIFFICULTY)
        line = ally_msg.call_args.args[0]
        self.assertIn(
            f"Rally Surge check vs rally difficulty {RALLY_BASE_DIFFICULTY} · Rally Success", line
        )

    def test_rally_without_a_tuning_rolls_nothing_even_with_a_rally_check(self) -> None:
        """A CheckType named Rally exists (the seed made it); no tuning, no roll (#4739)."""
        self.tuning.delete()
        action = declare_rally(self.rallier, self.ally)
        with force_check_outcome(self.success) as capture:
            _resolve_rally(self.rallier, action)
        self.assertIsNone(capture.check_type)

    def test_rally_with_an_inactive_check_type_rolls_nothing(self) -> None:
        """An inactive check type counts as unset, the rule Taunt follows (#4739)."""
        check_type = self.tuning.check_type
        check_type.is_active = False
        check_type.save()

        def reactivate() -> None:
            check_type.is_active = True

        self.addCleanup(reactivate)
        action = declare_rally(self.rallier, self.ally)
        with force_check_outcome(self.success) as capture:
            _resolve_rally(self.rallier, action)
        self.assertIsNone(capture.check_type)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_rally_failure_gives_smaller_or_no_surge_never_more(self) -> None:
        amounts = {}
        for outcome in (self.fail, self.partial, self.success, self.great):
            DramaticSurgeRecord.objects.all().delete()
            before = self._intensity()
            self._rally(outcome)
            amounts[outcome.name] = self._intensity() - before
        self.assertLessEqual(amounts["Rally Failure"], amounts["Rally Success"])
        self.assertLessEqual(amounts["Rally Failure"], amounts["Rally Great"])
        self.assertEqual(
            list(amounts.values()), sorted(amounts.values()), "a better rally never surges less"
        )

    def test_failed_rally_does_not_inspire(self) -> None:
        self._rally(self.fail)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.ally.character_sheet.character,
                condition__name=INSPIRED_SEED_TEMPLATE_NAME,
            ).exists()
        )

    def test_rally_with_no_tuning_does_nothing_and_does_not_crash(self) -> None:
        self.tuning.delete()
        self._rally(self.success)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.ally.character_sheet.character,
                condition__name=INSPIRED_SEED_TEMPLATE_NAME,
            ).exists()
        )

    def test_rally_without_a_curve_gives_no_surge(self) -> None:
        plain = CombatEncounterFactory(round_number=1, status=RoundStatus.DECLARING)
        rallier = CombatParticipantFactory(encounter=plain, status=ParticipantStatus.ACTIVE)
        ally = CombatParticipantFactory(encounter=plain, status=ParticipantStatus.ACTIVE)
        begin_engagement(ally.character_sheet.character, EngagementType.COMBAT, source=plain)
        action = declare_rally(rallier, ally)
        with force_check_outcome(self.success):
            _resolve_rally(rallier, action)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

"""Breaking a charm/turn hold under harm (#4091, task 9, Decision 16).

The PC who harms a held NPC rolls against the hold's strength; the NPC never
rolls (PCs roll, NPCs are targets). Difficulty scales with the hold's own
strength (severity x stage multiplier) against the harm's pressure (damage
dealt, scaled by the opponent's max health) and the opponent's resistance —
so a strong hold on a weak target survives a small hit, and a faded hold on
a hard-hit target breaks easily.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.factories import CombatOpponentFactory
from world.combat.models import CombatEncounter
from world.combat.services import apply_damage_to_opponent
from world.combat.tests.test_combat_technique_resolver import _build_resolver
from world.conditions.constants import Allegiance
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.conditions.models import ConditionInstance
from world.npc_services.allegiance_outcomes import attempt_allegiance_break
from world.traits.factories import CheckSystemSetupFactory


class AttemptAllegianceBreakTests(TestCase):
    """attempt_allegiance_break (Decision 16): the striker rolls, not the NPC."""

    def setUp(self) -> None:
        self.outcomes = CheckSystemSetupFactory.create()["outcomes"]
        self.break_check = CheckTypeFactory(name="Allegiance Break Harm 4091")
        self.charm = ConditionTemplateFactory(
            name="Charm Hold 4091",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=self.break_check,
        )
        self.pc_sheet = CharacterSheetFactory()
        # severity 6, no stage (multiplier 1.0), opponent level 1, max_health 100.
        self.opp = CombatOpponentFactory(level=1, health=100, max_health=100)
        self.instance = ConditionInstanceFactory(
            target=self.opp.objectdb,
            condition=self.charm,
            severity=6,
        )

    def test_strong_charm_on_weak_npc_holds_through_a_small_hit(self):
        with force_check_outcome(self.outcomes["failure"]) as capture:
            result = attempt_allegiance_break(
                striker=self.pc_sheet, opponent=self.opp, damage_dealt=5
            )
        self.assertFalse(result.broke)
        self.assertTrue(ConditionInstance.objects.filter(pk=self.instance.pk).exists())
        self.assertEqual(capture.check_type, self.break_check)
        self.assertGreater(capture.target_difficulty, 0)

    def test_faded_charm_on_resistant_npc_breaks_and_runs_stage_pool(self):
        pool = ConsequencePoolFactory(name="Faded hold settle 4091")
        success_row = ConsequenceFactory(
            outcome_tier=self.outcomes["success"], label="Faded hold settle: success"
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=success_row)
        # Fraying: severity_multiplier 0.25 -- a faded hold, easy to break even on
        # a resistant (higher-level) target, since the hold's own strength has
        # dropped to a quarter.
        stage = ConditionStageFactory(
            condition=self.charm,
            name="Fraying",
            stage_order=1,
            severity_multiplier=Decimal("0.25"),
            settle_consequence_pool=pool,
        )
        self.instance.current_stage = stage
        self.instance.save(update_fields=["current_stage"])
        self.opp.level = 10
        self.opp.save(update_fields=["level"])

        with force_check_outcome(self.outcomes["success"]):
            result = attempt_allegiance_break(
                striker=self.pc_sheet, opponent=self.opp, damage_dealt=20
            )
        self.assertTrue(result.broke)
        self.assertIsNotNone(result.ending)
        self.assertFalse(ConditionInstance.objects.filter(pk=self.instance.pk).exists())

    def test_bigger_hit_lowers_difficulty(self):
        with force_check_outcome(self.outcomes["failure"]) as small_capture:
            attempt_allegiance_break(striker=self.pc_sheet, opponent=self.opp, damage_dealt=5)
        with force_check_outcome(self.outcomes["failure"]) as big_capture:
            attempt_allegiance_break(striker=self.pc_sheet, opponent=self.opp, damage_dealt=50)
        self.assertLess(big_capture.target_difficulty, small_capture.target_difficulty)

    def test_npc_on_npc_damage_never_rolls(self):
        """apply_damage_to_opponent without allegiance_break_striker performs no check."""
        with patch("world.checks.services.perform_check") as mock_perform:
            apply_damage_to_opponent(self.opp, 20)
        mock_perform.assert_not_called()

    def test_break_never_opens_an_encounter(self):
        """A broken hold ends the condition through the settle pool -- it never
        starts a fight (Decision 21/8)."""
        before = CombatEncounter.objects.count()
        with force_check_outcome(self.outcomes["success"]):
            attempt_allegiance_break(striker=self.pc_sheet, opponent=self.opp, damage_dealt=50)
        self.assertEqual(CombatEncounter.objects.count(), before)


class CombatTechniqueResolverAllegianceBreakTest(TestCase):
    """A PC's technique damage on a held opponent rolls the break attempt too."""

    def setUp(self) -> None:
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full 4091 break"
        )

    def test_pc_technique_damage_calls_attempt_allegiance_break(self):
        resolver = _build_resolver(base_power=10)
        with patch("world.npc_services.allegiance_outcomes.attempt_allegiance_break") as mock_break:
            check = MagicMock(success_level=2)
            resolver._apply_damage(check, eff_intensity=5)
        mock_break.assert_called_once()
        kwargs = mock_break.call_args.kwargs
        self.assertEqual(kwargs["striker"], resolver.participant.character_sheet)
        self.assertEqual(kwargs["opponent"], resolver.action.focused_opponent_target)
        self.assertGreater(kwargs["damage_dealt"], 0)

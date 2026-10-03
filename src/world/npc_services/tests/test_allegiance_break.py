"""Breaking a charm/turn hold under harm (#4091, task 9, Decision 16).

The PC who harms a held NPC rolls against the hold's strength; the NPC never
rolls (PCs roll, NPCs are targets). Difficulty scales with the hold's own
strength (severity x stage multiplier) against the harm's pressure (damage
dealt, scaled by the opponent's max health) and the opponent's resistance —
so a strong hold on a weak target survives a small hit, and a faded hold on
a hard-hit target breaks easily.

Fix round 1: the break roll fires exactly once per opponent per PC action
(summed across every damage profile and any combo rider), never once per
``apply_damage_to_opponent`` call -- see ``test_pc_action_aggregation.py``-
style tests in ``PcActionAllegianceBreakAggregationTests`` below, and
``ResolveNpcActionOnOpponentTargetNeverRollsTest`` for the NPC-vs-opponent
path, which never rolls at all.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ActionCategory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
)
from world.combat.models import CombatEncounter, CombatRoundAction
from world.combat.services import (
    _resolve_npc_action_on_opponent_target,
    _resolve_pc_action,
    apply_damage_to_opponent,
)
from world.combat.types import ActionOutcome
from world.conditions.constants import Allegiance
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
    DamageTypeFactory,
)
from world.conditions.models import ConditionInstance
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.npc_services.allegiance_outcomes import attempt_allegiance_break
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals


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
        # Seeded by name, exactly how compute_resist_increment's real lookup finds
        # it (world.checks.services.compute_resist_increment:
        # ``CheckType.objects.filter(name="Composure", is_active=True).first()``).
        # Without this, resistance is always 0 regardless of opponent level --
        # review fix round 1 item 2.
        self.composure = CheckTypeFactory(name="Composure")
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
        # dropped to a quarter. With Composure now seeded (setUp), level 10 is a
        # REAL resistance of 50 (5 points/level x 10), not flavor text.
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

    def test_higher_opponent_level_lowers_difficulty_via_resistance(self):
        """Review item 2: resistance is real now that Composure is seeded.

        A higher-level opponent resists harder internally, which here REDUCES
        the striker's difficulty (the formula reads strength - resistance -
        pressure): a strong-willed NPC is already straining against the hold,
        so a PC's blow has less work left to do. Not a formula change -- this
        just proves the dependency is real and in the documented direction.
        """
        with force_check_outcome(self.outcomes["failure"]) as low_level_capture:
            attempt_allegiance_break(striker=self.pc_sheet, opponent=self.opp, damage_dealt=5)
        self.opp.level = 10
        self.opp.save(update_fields=["level"])
        with force_check_outcome(self.outcomes["failure"]) as high_level_capture:
            attempt_allegiance_break(striker=self.pc_sheet, opponent=self.opp, damage_dealt=5)
        self.assertLess(high_level_capture.target_difficulty, low_level_capture.target_difficulty)

    def test_scale_level_twelve_zeroes_a_severity_six_hold_with_no_damage_pressure(self):
        """Review item 2 scale check: can level points alone zero out a severity-6
        hold at a realistic level? Yes, at level 12 (of the 1-30 range), with
        zero damage pressure needed. Numbers (CHARM_STRENGTH_POINTS_PER_SEVERITY=10,
        LEVEL_POINTS_PER_LEVEL=5, EFFORT_CHECK_MODIFIER[MEDIUM]=0):

            strength   = 6 (severity) x 10            = 60
            resistance = 12 (level) x 5 + 0 (effort)   = 60
            pressure   = harm_pressure_points(1, 100)  = 0
            difficulty = max(0, 60 - 60 - 0)           = 0

        This is reported, not asserted as a bug: the formula is unchanged per
        the review's instruction ("do not change the formula; the controller
        will rule on it"). Recorded here as executable proof of the numbers.
        """
        self.opp.level = 12
        self.opp.save(update_fields=["level"])
        with force_check_outcome(self.outcomes["failure"]) as capture:
            attempt_allegiance_break(striker=self.pc_sheet, opponent=self.opp, damage_dealt=1)
        self.assertEqual(capture.target_difficulty, 0)

    def test_npc_on_npc_damage_never_rolls(self):
        """apply_damage_to_opponent without allegiance_break_striker performs no check.

        (Fix round 1: the roll no longer lives inside apply_damage_to_opponent at
        all -- it is aggregated once per PC action in
        _attempt_allegiance_breaks_for_action, called only from _resolve_pc_action.
        This call path can never reach it.)
        """
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


class PcActionAllegianceBreakAggregationTests(TestCase):
    """Fix round 1 (#4091 task 9): one break-attempt roll per opponent per PC
    action, aggregated across every damage profile AND any combo rider -- never
    once per ``apply_damage_to_opponent`` call.

    Drives the real ``_resolve_pc_action`` orchestrator (the function both the
    technique pipeline's ``_apply_profiles_to_target`` and ``_apply_combo_rider``
    report into via ``outcome.damage_results``), with ``perform_check`` mocked to
    a guaranteed full-success offense roll so the resulting damage numbers are
    deterministic, and ``attempt_allegiance_break`` mocked so this test proves the
    CALL SHAPE (count + summed pressure) rather than re-exercising the break
    roll's own internals (covered by ``AttemptAllegianceBreakTests`` above).
    """

    def setUp(self) -> None:
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full 4091 round1"
        )
        self.break_check = CheckTypeFactory(name="Allegiance Break Harm Round1 4091")
        self.charm = ConditionTemplateFactory(
            name="Charm Hold Round1 4091",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=self.break_check,
        )
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.opp = CombatOpponentFactory(
            encounter=self.encounter, health=500, max_health=500, soak_value=0, level=1
        )
        ConditionInstanceFactory(target=self.opp.objectdb, condition=self.charm, severity=6)
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=self.sheet, current=50, maximum=50)
        CharacterEngagementFactory(character=self.sheet)

    def _make_action(
        self, *, second_profile_damage: int | None = None, combo=None
    ) -> CombatRoundAction:
        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(base_power=10),
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        if second_profile_damage is not None:
            TechniqueDamageProfileFactory(
                technique=technique,
                base_damage=second_profile_damage,
                damage_type=DamageTypeFactory(),
                minimum_success_level=1,
            )
        return CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=self.opp,
            combo_upgrade=combo,
        )

    def test_multi_profile_blow_rolls_once_with_summed_pressure(self):
        action = self._make_action(second_profile_damage=5)
        with (
            patch("world.combat.services.perform_check") as mock_perform,
            patch("world.npc_services.allegiance_outcomes.attempt_allegiance_break") as mock_break,
        ):
            mock_perform.return_value = MagicMock(success_level=2)
            _resolve_pc_action(self.participant, action)
        mock_break.assert_called_once()
        kwargs = mock_break.call_args.kwargs
        self.assertEqual(kwargs["opponent"], self.opp)
        self.assertEqual(kwargs["striker"], self.sheet)
        # 10 (auto-seeded profile) + 5 (second profile), soak 0, SL2 multiplier 1.0.
        self.assertEqual(kwargs["damage_dealt"], 15)

    def test_combo_rider_plus_a_profile_rolls_once(self):
        combo = ComboDefinitionFactory(bonus_damage=7, bypass_soak=True)
        action = self._make_action(combo=combo)
        with (
            patch("world.combat.services.perform_check") as mock_perform,
            patch("world.npc_services.allegiance_outcomes.attempt_allegiance_break") as mock_break,
        ):
            mock_perform.return_value = MagicMock(success_level=2)
            _resolve_pc_action(self.participant, action)
        mock_break.assert_called_once()
        kwargs = mock_break.call_args.kwargs
        # 10 (the technique's own profile) + 7 (the combo rider), summed once.
        self.assertEqual(kwargs["damage_dealt"], 17)


class ResolveNpcActionOnOpponentTargetNeverRollsTest(TestCase):
    """An NPC's own attack on an opponent target never rolls a break attempt.

    Decision 16 is PC-only -- drives the real
    ``_resolve_npc_action_on_opponent_target`` (an ALLY summon or a charmed/
    turned NPC attacking a hostile opponent; #1584, #4091), never
    ``_resolve_pc_action``, so the aggregation hook (which lives only in the
    latter) is structurally unreachable here.
    """

    def setUp(self) -> None:
        self.break_check = CheckTypeFactory(name="Allegiance Break Harm NPC 4091")
        self.charm = ConditionTemplateFactory(
            name="Charm Hold NPC 4091",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=self.break_check,
        )
        self.encounter = CombatEncounterFactory()
        self.target_opponent = CombatOpponentFactory(
            encounter=self.encounter, health=100, max_health=100, soak_value=0
        )
        ConditionInstanceFactory(
            target=self.target_opponent.objectdb, condition=self.charm, severity=6
        )
        self.attacker = CombatOpponentFactory(encounter=self.encounter)
        self.npc_action = CombatOpponentActionFactory(
            opponent=self.attacker, threat_entry__base_damage=20
        )

    def test_npc_action_on_opponent_target_never_rolls(self):
        outcome = ActionOutcome(entity_type="npc", entity_label="Attacker")
        with patch("world.checks.services.perform_check") as mock_perform:
            _resolve_npc_action_on_opponent_target(
                self.target_opponent,
                opponent=self.attacker,
                npc_action=self.npc_action,
                outcome=outcome,
                conditions=[],
                condition_applications=[],
            )
        mock_perform.assert_not_called()
        self.assertTrue(outcome.damage_results)
        self.assertGreater(outcome.damage_results[0].damage_dealt, 0)

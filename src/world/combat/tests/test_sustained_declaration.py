"""Tests for PC sustained-action declaration + the Concentration absorption budget (#2705).

Covers ``roll_sustained_absorption_budget``'s ladder/clamp math and
``declare_action``'s integration: creating, idempotently re-declaring, and
blocking around a ``SustainedAction`` while one is pending (decision D2).

The condition-modifier test is the important one: it proves the 26 authored
Concentration ``ConditionCheckModifier`` rows (lore-repo content, not seeded in
arxii) are actually live via ``perform_check_with_modifiers`` — the same
``collect_check_modifiers`` -> ``condition_contributions`` ->
``get_check_modifier`` chain #2697's ``test_condition_modifies_cast.py`` proved
for standalone technique casts.
"""

from __future__ import annotations

import re

from django.test import TestCase

from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import CONCENTRATION_CHECK_TYPE_NAME, SustainedKind
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatEncounter, CombatParticipant, SustainedAction
from world.combat.services import declare_action, roll_sustained_absorption_budget
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.fatigue.constants import EffortLevel
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.scenes.constants import RoundStatus
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckRankFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart
from world.vitals.models import CharacterVitals


def _make_declaring_encounter(round_number: int = 1) -> CombatEncounter:
    return CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=round_number)


def _make_participant(encounter: CombatEncounter) -> CombatParticipant:
    participant = CombatParticipantFactory(encounter=encounter)
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet, health=100, max_health=100
    )
    return participant


class _SustainedTestBase(TestCase):
    """Shared Concentration ``CheckType`` — built with factories (#2705).

    ``Concentration`` is authored ONLY in the lore repo, not in arxii seeds, so
    every test in this module builds its own copy with
    ``CheckTypeFactory``/``CheckCategoryFactory`` rather than relying on seed
    data.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.concentration_category = CheckCategoryFactory(name="sustained-composure-checks")
        cls.concentration_check_type = CheckTypeFactory(
            name=CONCENTRATION_CHECK_TYPE_NAME, category=cls.concentration_category
        )
        cls.gift = GiftFactory()
        cls.effect_type_buff = EffectTypeFactory(name="SustainedBuffEffect", base_power=None)

    def setUp(self) -> None:
        super().setUp()
        # Defensive even for classes that don't create ResultChart rows
        # themselves — the cache is process-global and another test class in
        # this module (the condition-modifier class) does create charts.
        ResultChart.clear_cache()


class SustainedTechniqueDeclarationTests(_SustainedTestBase):
    """declare_action's integration with SustainedAction for windup_rounds > 0."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = _make_declaring_encounter(round_number=1)
        self.participant = _make_participant(self.encounter)

    def test_windup_technique_creates_sustained_action(self) -> None:
        """A windup_rounds=2 technique creates exactly one SustainedAction with
        resolves_round == declared_round + 2 and no damage-ramp fields (D1)."""
        technique = TechniqueFactory(
            gift=self.gift, effect_type=self.effect_type_buff, windup_rounds=2
        )
        action = declare_action(
            self.participant,
            focused_action=technique,
            effort_level=EffortLevel.MEDIUM,
        )

        self.assertEqual(SustainedAction.objects.count(), 1)
        sustained = SustainedAction.objects.get()
        self.assertEqual(sustained.sustained_kind, SustainedKind.TECHNIQUE)
        self.assertEqual(sustained.technique_id, technique.pk)
        self.assertIsNone(sustained.ritual_id)
        self.assertEqual(sustained.declared_action_id, action.pk)
        self.assertEqual(sustained.declared_round, 1)
        self.assertEqual(sustained.resolves_round, 3)
        self.assertEqual(sustained.downgrades, 0)
        self.assertGreaterEqual(sustained.absorption_budget, 0)
        self.assertLessEqual(sustained.absorption_budget, 4)
        # D1: no damage_scale / ramp field on the row at all.
        self.assertFalse(hasattr(sustained, "damage_scale"))

    def test_windup_rounds_zero_creates_no_sustained_action(self) -> None:
        """windup_rounds=0 is the inertness guarantee: no SustainedAction at all."""
        technique = TechniqueFactory(
            gift=self.gift, effect_type=self.effect_type_buff, windup_rounds=0
        )
        declare_action(
            self.participant,
            focused_action=technique,
            effort_level=EffortLevel.MEDIUM,
        )
        self.assertEqual(SustainedAction.objects.count(), 0)

    def test_redeclaring_same_round_replaces_not_stacks(self) -> None:
        """Re-declaring the same round's action never stacks a second row."""
        technique = TechniqueFactory(
            gift=self.gift, effect_type=self.effect_type_buff, windup_rounds=2
        )
        declare_action(self.participant, focused_action=technique, effort_level=EffortLevel.MEDIUM)
        self.assertEqual(SustainedAction.objects.count(), 1)

        declare_action(self.participant, focused_action=technique, effort_level=EffortLevel.HIGH)
        self.assertEqual(SustainedAction.objects.count(), 1)

    def test_redeclaring_to_non_windup_technique_clears_sustained_action(self) -> None:
        """Switching to a non-windup technique on re-declaration clears the row."""
        windup_technique = TechniqueFactory(
            gift=self.gift, effect_type=self.effect_type_buff, windup_rounds=2
        )
        declare_action(
            self.participant, focused_action=windup_technique, effort_level=EffortLevel.MEDIUM
        )
        self.assertEqual(SustainedAction.objects.count(), 1)

        instant_technique = TechniqueFactory(
            gift=self.gift, effect_type=self.effect_type_buff, windup_rounds=0
        )
        declare_action(
            self.participant, focused_action=instant_technique, effort_level=EffortLevel.MEDIUM
        )
        self.assertEqual(SustainedAction.objects.count(), 0)

    def test_declaring_in_intervening_round_raises(self) -> None:
        """Declaring while a SustainedAction is pending raises, naming the held subject (D2)."""
        technique = TechniqueFactory(
            gift=self.gift, effect_type=self.effect_type_buff, windup_rounds=2
        )
        declare_action(self.participant, focused_action=technique, effort_level=EffortLevel.MEDIUM)
        sustained = SustainedAction.objects.get()

        # Advance to the next round — still strictly before resolves_round (3).
        self.encounter.round_number = 2
        self.encounter.save(update_fields=["round_number"])

        with self.assertRaisesRegex(ValueError, re.escape(sustained.subject_name)):
            declare_action(self.participant, effort_level=EffortLevel.MEDIUM)


class SustainedAbsorptionLadderTests(_SustainedTestBase):
    """roll_sustained_absorption_budget's clamp(BASE + success_level, MIN, MAX) ladder (D3)."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = _make_declaring_encounter(round_number=1)
        self.participant = _make_participant(self.encounter)

    def test_budget_ladder(self) -> None:
        cases = [(-2, 0), (-1, 1), (0, 2), (1, 3), (2, 4)]
        for success_level, expected_budget in cases:
            with self.subTest(success_level=success_level):
                outcome = CheckOutcomeFactory(success_level=success_level)
                with force_check_outcome(outcome):
                    budget, returned_outcome = roll_sustained_absorption_budget(self.participant)
                self.assertEqual(budget, expected_budget)
                self.assertEqual(returned_outcome, outcome)

    def test_budget_clamped_at_max(self) -> None:
        """A wide authored ladder's crit success (success_level=7) clamps to 4."""
        outcome = CheckOutcomeFactory(success_level=7)
        with force_check_outcome(outcome):
            budget, _ = roll_sustained_absorption_budget(self.participant)
        self.assertEqual(budget, 4)

    def test_budget_clamped_at_min(self) -> None:
        """A wide authored ladder's catastrophic failure (success_level=-9) clamps to 0."""
        outcome = CheckOutcomeFactory(success_level=-9)
        with force_check_outcome(outcome):
            budget, _ = roll_sustained_absorption_budget(self.participant)
        self.assertEqual(budget, 0)


class SustainedAbsorptionConditionModifierTests(_SustainedTestBase):
    """The payoff test: a real ConditionCheckModifier on Concentration moves the budget.

    Every other trait/aspect/capability/perk contribution is 0 for a bare test
    character with no CharacterClassLevel/CharacterPathHistory/CheckTypeTrait/
    CheckTypeCapabilityModifier rows (verified against ``_compute_check_
    breakdown``'s callees), so the participant's baseline ``total_points`` is
    exactly ``LEVEL_POINTS_PER_LEVEL * level == 5 * 1 == 5`` — deterministic,
    no forced outcome needed. ``CheckRank.min_points`` is a
    ``PositiveIntegerField`` (no negative tiers), so the setup uses ONE rank
    at ``min_points=5``: baseline total_points (5) qualifies for it
    (``rank_difference=1`` against ``target_difficulty=0``'s implicit rank 0),
    while a modifier that pushes the total below 0 makes NO rank qualify
    (``CheckRank.get_rank_for_points`` returns ``None``, which the breakdown
    formula treats as rank 0 — ``rank_difference=0``). Two ResultCharts with a
    single 1-100 roll-band make the outcome independent of the dice roll — so
    this test exercises the REAL ``perform_check_with_modifiers`` ->
    ``collect_check_modifiers`` -> ``condition_contributions`` ->
    ``get_check_modifier`` chain end to end, not a forced outcome
    (``force_check_outcome`` bypasses modifiers entirely, which is exactly why
    the ladder tests above use it and this one does not).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.rank_baseline = CheckRankFactory(rank=1, min_points=5, name="SustainedBaseline")
        cls.outcome_success = CheckOutcomeFactory(
            name="Sustained Concentration Success", success_level=1
        )
        cls.outcome_failure = CheckOutcomeFactory(
            name="Sustained Concentration Failure", success_level=-3
        )
        # rank_difference=1: baseline total_points (5) reaches rank_baseline
        # while target_difficulty=0 stays at the implicit rank 0.
        cls.chart_at_baseline = ResultChartFactory(rank_difference=1, name="SustainedAtBaseline")
        ResultChartOutcomeFactory(
            chart=cls.chart_at_baseline, outcome=cls.outcome_success, min_roll=1, max_roll=100
        )
        # rank_difference=0: a large enough negative modifier drops total_points
        # below 0, so no CheckRank qualifies and the roller falls back to rank 0.
        cls.chart_below_baseline = ResultChartFactory(
            rank_difference=0, name="SustainedBelowBaseline"
        )
        ResultChartOutcomeFactory(
            chart=cls.chart_below_baseline, outcome=cls.outcome_failure, min_roll=1, max_roll=100
        )

    def setUp(self) -> None:
        super().setUp()
        self.encounter = _make_declaring_encounter(round_number=1)
        self.participant = _make_participant(self.encounter)

    def test_condition_modifier_lowers_budget(self) -> None:
        budget_without, _ = roll_sustained_absorption_budget(self.participant)
        # clamp(2 + success_level=1, 0, 4) == 3 — rank_difference 1 -> chart_at_baseline.
        self.assertEqual(budget_without, 3)

        stressed = ConditionTemplateFactory(name="stressed-sustained-e2e")
        ConditionCheckModifierFactory(
            condition=stressed,
            check_type=self.concentration_check_type,
            check_category=None,
            modifier_value=-10,
        )
        ConditionInstanceFactory(
            target=self.participant.character_sheet.character,
            condition=stressed,
        )

        budget_with, _ = roll_sustained_absorption_budget(self.participant)
        # total_points = 5 - 10 = -5: no CheckRank qualifies, rank_difference
        # drops to 0 -> chart_below_baseline -> success_level=-3.
        # clamp(2 + -3, 0, 4) == 0.
        self.assertEqual(budget_with, 0)
        self.assertLessEqual(budget_with, budget_without)

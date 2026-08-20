"""Tests for the technique combat-power evaluator (#3279 Task 1).

Covers the damage payload valuator, the baseline-vs-amplified power comparison
(via the pure helpers extracted from ``power_terms.py`` in this same task),
windup division, the ``weapon_scaled`` flag, effective-anima-cost-driven
``de_per_anima``, and a regression guard on the extracted pure helpers
themselves. Buffs/debuffs/control/mitigation/heals/dispel/capability payloads
are Task 2's scope — not covered here.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic.factories import TechniqueDamageProfileFactory, TechniqueFactory
from world.magic.services.power_terms import (
    blend_power_contribution,
    get_covenant_role_blend_config,
    specialty_power_contribution,
)
from world.magic.services.technique_power_eval import evaluate_technique
from world.magic.services.techniques import calculate_effective_anima_cost
from world.magic.types.technique_power import EvalContext, ReferenceFrame
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckRankFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart

_PLACEHOLDER_REFERENCE = ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=0.0, source_label="test")


class TechniquePowerEvalDamageTests(TestCase):
    """Damage valuator + power/anima plumbing (#3279 Task 1)."""

    @classmethod
    def setUpTestData(cls) -> None:
        # A single CheckRank at rank=0/min_points=0 puts EvalContext's default
        # roller_points=25 and target_difficulty=25 at the same rank, so the
        # derived rank_difference is 0 — matching the chart below.
        CheckRankFactory(rank=0, min_points=0)

        # Two-band, even-split chart at rank_difference=0 (mirrors
        # web/admin/tests/test_checks_analytics.py's setup pattern): SL 1 on
        # rolls 1-50, SL 3 on rolls 51-100 -> P=0.5 each.
        cls.sl1 = CheckOutcomeFactory(name="Partial", success_level=1)
        cls.sl3 = CheckOutcomeFactory(name="Full", success_level=3)
        chart = ResultChartFactory(rank_difference=0, name="Even")
        ResultChartOutcomeFactory(chart=chart, outcome=cls.sl1, min_roll=1, max_roll=50)
        ResultChartOutcomeFactory(chart=chart, outcome=cls.sl3, min_roll=51, max_roll=100)

        # One multiplier row covering both bands (SL >= 1 -> x1.00) keeps the
        # hand-computed expectation in test_one below simple.
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("1.00"))

    def setUp(self) -> None:
        # ResultChart._chart_cache is a process-level dict, not
        # transaction-scoped — clear it so this class's own chart wins.
        ResultChart.clear_cache()

    def _technique(self, **kwargs):
        kwargs.setdefault("intensity", 4)
        kwargs.setdefault("damage_profile", False)
        return TechniqueFactory(**kwargs)

    def test_one_damage_profile_matches_hand_computed_expectation(self) -> None:
        """budget(SL1)=9, budget(SL3)=13; E[DE] = 0.5*9 + 0.5*13 = 11.0 (mult x1.00)."""
        technique = self._technique(intensity=4)
        TechniqueDamageProfileFactory(
            technique=technique,
            base_damage=5,
            damage_intensity_multiplier=Decimal("1.00"),
            damage_per_extra_sl=2,
            minimum_success_level=1,
        )

        report = evaluate_technique(technique, EvalContext(), _PLACEHOLDER_REFERENCE)

        budget_sl1 = 5 + int(Decimal("1.00") * 4) + 2 * max(0, 1 - 1)
        budget_sl3 = 5 + int(Decimal("1.00") * 4) + 2 * max(0, 3 - 1)
        expected_de = 0.5 * budget_sl1 * 1.0 + 0.5 * budget_sl3 * 1.0

        self.assertEqual(report.baseline_power, 4)
        self.assertAlmostEqual(report.baseline_de, expected_de, places=9)
        self.assertEqual(len(report.valuations), 1)
        self.assertEqual(report.valuations[0].kind, "damage")

    def test_amplified_power_matches_role_band_pure_helpers(self) -> None:
        """amplified_power - baseline_power == int(blend) + int(specialty) at thread_level."""
        technique = self._technique(intensity=4)
        TechniqueDamageProfileFactory(technique=technique, base_damage=5, minimum_success_level=1)
        context = EvalContext(thread_level=3)

        report = evaluate_technique(technique, context, _PLACEHOLDER_REFERENCE)

        config = get_covenant_role_blend_config()
        expected_blend = int(
            blend_power_contribution(context.thread_level, Decimal(1), config.multiplier_tenths)
        )
        expected_specialty = int(specialty_power_contribution(context.thread_level, 10))

        self.assertEqual(
            report.amplified_power - report.baseline_power,
            expected_blend + expected_specialty,
        )

    def test_windup_divides_de_and_weapon_scaled_flag_set(self) -> None:
        technique = self._technique(intensity=4, windup_rounds=2)
        TechniqueDamageProfileFactory(
            technique=technique,
            base_damage=5,
            damage_intensity_multiplier=Decimal("1.00"),
            damage_per_extra_sl=2,
            minimum_success_level=1,
            uses_equipped_weapon=True,
        )

        report = evaluate_technique(technique, EvalContext(), _PLACEHOLDER_REFERENCE)

        budget_sl1 = 5 + int(Decimal("1.00") * 4) + 2 * max(0, 1 - 1)
        budget_sl3 = 5 + int(Decimal("1.00") * 4) + 2 * max(0, 3 - 1)
        raw_de = 0.5 * budget_sl1 * 1.0 + 0.5 * budget_sl3 * 1.0
        expected_de = raw_de / 3  # divided by (1 + windup_rounds)

        self.assertAlmostEqual(report.baseline_de, expected_de, places=9)
        self.assertIn("windup:2", report.flags)
        self.assertIn("weapon_scaled", report.flags)

    def test_de_per_anima_uses_effective_control_delta_cost(self) -> None:
        technique = self._technique(intensity=4, control=6, anima_cost=10)
        TechniqueDamageProfileFactory(technique=technique, base_damage=5, minimum_success_level=1)

        report = evaluate_technique(technique, EvalContext(), _PLACEHOLDER_REFERENCE)

        effective = calculate_effective_anima_cost(
            base_cost=10,
            runtime_intensity=4,
            runtime_control=6,
            current_anima=1_000_000,
            lethal=True,
        )

        self.assertEqual(report.effective_anima, effective.effective_cost)
        self.assertAlmostEqual(
            report.de_per_anima,
            report.baseline_de / max(1, effective.effective_cost),
            places=9,
        )


class PowerTermPureHelperExtractionTests(TestCase):
    """Regression guard: extracted helpers reproduce the pre-refactor inline arithmetic (#3279)."""

    def test_blend_power_contribution_matches_inline_formula(self) -> None:
        thread_level, blend_weight, multiplier_tenths = 7, Decimal("0.5"), 20
        expected = Decimal(thread_level) * blend_weight * multiplier_tenths / 10
        self.assertEqual(
            blend_power_contribution(thread_level, blend_weight, multiplier_tenths), expected
        )

    def test_blend_power_contribution_second_sample(self) -> None:
        thread_level, blend_weight, multiplier_tenths = 12, Decimal(1), 15
        expected = Decimal(thread_level) * blend_weight * multiplier_tenths / 10
        self.assertEqual(
            blend_power_contribution(thread_level, blend_weight, multiplier_tenths), expected
        )

    def test_specialty_power_contribution_matches_inline_formula(self) -> None:
        thread_level, multiplier_tenths = 7, 15
        expected = Decimal(thread_level) * multiplier_tenths / 10
        self.assertEqual(specialty_power_contribution(thread_level, multiplier_tenths), expected)

    def test_specialty_power_contribution_second_sample(self) -> None:
        thread_level, multiplier_tenths = 20, 10
        expected = Decimal(thread_level) * multiplier_tenths / 10
        self.assertEqual(specialty_power_contribution(thread_level, multiplier_tenths), expected)

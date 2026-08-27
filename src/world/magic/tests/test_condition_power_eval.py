"""Tests for the standalone condition -> DE valuator (#3390).

Regression-anchors the two reused formula cores against the shipped Defend content
(mitigation) and a factory DoT row, mirroring the technique-layer's own regression
tests at ``test_technique_power_eval_valuators.py`` — same numbers, a different entry
point (``evaluate_condition`` instead of ``evaluate_technique``).
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.defend_content import DEFEND_PASSIVE_NAME, ensure_defend_content
from world.conditions.factories import (
    ConditionDamageOverTimeFactory,
    ConditionTemplateFactory,
)
from world.magic.models.techniques import Technique
from world.magic.services.condition_power_eval import evaluate_condition
from world.magic.types.technique_power import EvalContext, ReferenceFrame, ValuationProvenance
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckRankFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart

_KIND_MITIGATION = "mitigation"
_KIND_DEBUFF = "debuff"


class ConditionPowerEvalTestCase(TestCase):
    """Shared even-split SL1/SL3 matchup chart, mirroring the technique suite's setup."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckRankFactory(rank=0, min_points=0)
        cls.sl1 = CheckOutcomeFactory(name="Partial", success_level=1)
        cls.sl3 = CheckOutcomeFactory(name="Full", success_level=3)
        chart = ResultChartFactory(rank_difference=0, name="Even")
        ResultChartOutcomeFactory(chart=chart, outcome=cls.sl1, min_roll=1, max_roll=50)
        ResultChartOutcomeFactory(chart=chart, outcome=cls.sl3, min_roll=51, max_roll=100)

    def setUp(self) -> None:
        ResultChart.clear_cache()


class MitigationParityTests(ConditionPowerEvalTestCase):
    """Condition mitigation parity anchor (#3390 Testing section)."""

    def test_defend_content_values_as_50_percent_mitigation_standalone(self) -> None:
        """`evaluate_condition` on the shipped Defend condition must match the exact
        formula the technique-layer regression test asserts at the same duration:
        `(1 - 0.5) * reference.incoming_dpr * duration_rounds`.
        """
        ensure_defend_content()
        technique = Technique.objects.get(name=DEFEND_PASSIVE_NAME)
        row = technique.condition_applications.get()
        template = row.condition

        duration_rounds = 3
        reference = ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=30.0, source_label="test")

        report = evaluate_condition(
            template,
            at_severity=5,
            duration_rounds=duration_rounds,
            reference=reference,
        )

        mitigation_rows = [v for v in report.valuations if v.kind == _KIND_MITIGATION]
        self.assertEqual(len(mitigation_rows), 1)
        self.assertEqual(mitigation_rows[0].provenance, ValuationProvenance.PARSED)
        expected_value = (1 - 0.5) * reference.incoming_dpr * duration_rounds
        self.assertAlmostEqual(mitigation_rows[0].value, expected_value, places=6)
        self.assertAlmostEqual(report.total_de, expected_value, places=6)


class DotAnchorTests(ConditionPowerEvalTestCase):
    """Condition DoT anchor (#3390 Testing section)."""

    def test_dot_matches_base_damage_x_severity_x_duration(self) -> None:
        template = ConditionTemplateFactory()
        dot = ConditionDamageOverTimeFactory(
            condition=template,
            stage=None,
            base_damage=4,
            scales_with_severity=True,
            scales_with_stacks=True,
        )

        at_severity = 6
        duration_rounds = 2
        reference = ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=0.0, source_label="test")

        report = evaluate_condition(
            template,
            at_severity=at_severity,
            duration_rounds=duration_rounds,
            reference=reference,
        )

        debuff_rows = [v for v in report.valuations if v.kind == _KIND_DEBUFF]
        self.assertEqual(len(debuff_rows), 1)
        self.assertEqual(debuff_rows[0].provenance, ValuationProvenance.FORMULA)
        expected_value = dot.base_damage * at_severity * duration_rounds
        self.assertAlmostEqual(debuff_rows[0].value, expected_value, places=6)


class UnpriceableFallbackTests(ConditionPowerEvalTestCase):
    """A condition with no priceable payload gets one named UNPRICEABLE row, not a crash."""

    def test_bare_condition_with_no_payload_is_unpriceable(self) -> None:
        template = ConditionTemplateFactory()
        reference = ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=0.0, source_label="test")

        report = evaluate_condition(template, at_severity=5, duration_rounds=1, reference=reference)

        self.assertEqual(report.total_de, 0.0)
        self.assertEqual(len(report.valuations), 1)
        self.assertEqual(report.valuations[0].provenance, ValuationProvenance.UNPRICEABLE)


class TeamLaneGapTests(ConditionPowerEvalTestCase):
    """Decision 6: the team-damage-percent lane surfaces as a named UNPRICEABLE gap."""

    def test_team_lane_condition_flags_gap_not_silent_zero(self) -> None:
        from world.conditions.factories import ConditionModifierEffectFactory
        from world.mechanics.factories import TeamDamagePercentTargetFactory

        template = ConditionTemplateFactory()
        ConditionModifierEffectFactory(
            condition=template,
            modifier_target=TeamDamagePercentTargetFactory(),
            scales_with_severity=True,
        )
        reference = ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=0.0, source_label="test")

        report = evaluate_condition(template, at_severity=5, duration_rounds=1, reference=reference)

        self.assertIn("team_lane_excluded", report.flags)
        unpriceable = [
            v for v in report.valuations if v.provenance == ValuationProvenance.UNPRICEABLE
        ]
        self.assertEqual(len(unpriceable), 1)


class ReferenceFrameSharingTests(ConditionPowerEvalTestCase):
    """Decision 2: conditions and capabilities anchor on the exact same reference frame."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from world.conditions.factories import DamageSuccessLevelMultiplierFactory
        from world.magic.factories import TechniqueFactory

        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=1)
        # damage_profile=True (the factory default) makes this an "attack technique"
        # compute_reference_frame's median bootstrap picks up, so the reference is a
        # real nonzero figure rather than the trivial "no attack techniques" 0.0 case.
        TechniqueFactory(intensity=8)

    def test_compute_reference_frame_is_deterministic_across_call_sites(self) -> None:
        """Two independent `compute_reference_frame(context)` calls - one for each
        instrument's own panel-analytics layer - must produce the identical
        `outgoing_dpr`/`incoming_dpr`, proving the shared computation doesn't
        silently redefine the currency between the condition and capability panels.
        """
        from world.magic.services import de_valuation

        context = EvalContext()
        reference_a = de_valuation.compute_reference_frame(context)
        reference_b = de_valuation.compute_reference_frame(context)

        self.assertGreater(reference_a.outgoing_dpr, 0.0)
        self.assertEqual(reference_a.outgoing_dpr, reference_b.outgoing_dpr)
        self.assertEqual(reference_a.incoming_dpr, reference_b.incoming_dpr)
        self.assertEqual(reference_a.source_label, reference_b.source_label)

    def test_shared_reference_frame_threads_into_both_evaluators(self) -> None:
        from world.conditions.factories import CapabilityTypeFactory
        from world.magic.services import capability_power_eval, de_valuation

        context = EvalContext()
        reference = de_valuation.compute_reference_frame(context)

        template = ConditionTemplateFactory()
        capability = CapabilityTypeFactory()

        condition_report = evaluate_condition(
            template,
            at_severity=5,
            duration_rounds=1,
            reference=reference,
            context=context,
        )
        capability_report = capability_power_eval.evaluate_capability(
            capability, context=context, reference=reference
        )

        self.assertIsNotNone(condition_report)
        self.assertIsNotNone(capability_report)

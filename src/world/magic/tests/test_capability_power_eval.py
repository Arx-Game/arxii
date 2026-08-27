"""Tests for the capability -> DE valuator (#3390).

Anchors Decision 5 ("no authored bridge = 0 DE with a flag, never a crash") and the
priced-row path (Decision 3's linear marginal-rate estimate), mirroring the technique
and condition suites' regression-anchor style.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.checks.factories import CheckTypeCapabilityModifierFactory, CheckTypeFactory
from world.conditions.factories import CapabilityTypeFactory, DamageSuccessLevelMultiplierFactory
from world.magic.services.capability_power_eval import (
    NO_AUTHORED_BRIDGE_FLAG,
    evaluate_capability,
)
from world.magic.types.technique_power import EvalContext, ReferenceFrame, ValuationProvenance
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckRankFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart

_KIND_CHECK_BRIDGE = "check_bridge"


class CapabilityPowerEvalTestCase(TestCase):
    """Shared even-split SL1/SL3 matchup chart, mirroring the technique suite's setup."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckRankFactory(rank=0, min_points=0)
        cls.sl1 = CheckOutcomeFactory(name="Partial", success_level=1)
        cls.sl3 = CheckOutcomeFactory(name="Full", success_level=3)
        chart = ResultChartFactory(rank_difference=0, name="Even")
        ResultChartOutcomeFactory(chart=chart, outcome=cls.sl1, min_roll=1, max_roll=50)
        ResultChartOutcomeFactory(chart=chart, outcome=cls.sl3, min_roll=51, max_roll=100)
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=1)

    def setUp(self) -> None:
        ResultChart.clear_cache()


class NoAuthoredBridgeTests(CapabilityPowerEvalTestCase):
    """Capability no-bridge anchor (#3390 Testing section, Decision 5)."""

    def test_zero_rows_prices_zero_with_flag(self) -> None:
        capability = CapabilityTypeFactory()
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=10.0, incoming_dpr=10.0, source_label="test")

        report = evaluate_capability(capability, context=context, reference=reference)

        self.assertEqual(report.total_de, 0.0)
        self.assertEqual(report.flags, (NO_AUTHORED_BRIDGE_FLAG,))
        self.assertEqual(len(report.valuations), 1)
        self.assertEqual(report.valuations[0].provenance, ValuationProvenance.UNPRICEABLE)


class PricedBridgeTests(CapabilityPowerEvalTestCase):
    """Capability priced anchor (#3390 Testing section, Decision 3)."""

    def test_positive_weight_prices_positive_and_sums_across_rows(self) -> None:
        capability = CapabilityTypeFactory()
        check_type_a = CheckTypeFactory()
        check_type_b = CheckTypeFactory()
        CheckTypeCapabilityModifierFactory(
            capability=capability, check_type=check_type_a, weight=Decimal("2.00")
        )
        CheckTypeCapabilityModifierFactory(
            capability=capability, check_type=check_type_b, weight=Decimal("3.00")
        )
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=10.0, incoming_dpr=10.0, source_label="test")

        report = evaluate_capability(capability, context=context, reference=reference)

        bridge_rows = [v for v in report.valuations if v.kind == _KIND_CHECK_BRIDGE]
        self.assertEqual(len(bridge_rows), 2)
        for row in bridge_rows:
            self.assertEqual(row.provenance, ValuationProvenance.ESTIMATE)
            self.assertGreater(row.value, 0.0)
        self.assertNotEqual(report.flags, (NO_AUTHORED_BRIDGE_FLAG,))
        self.assertAlmostEqual(report.total_de, sum(v.value for v in bridge_rows), places=6)

    def test_negative_weight_prices_negative(self) -> None:
        capability = CapabilityTypeFactory()
        check_type = CheckTypeFactory()
        CheckTypeCapabilityModifierFactory(
            capability=capability, check_type=check_type, weight=Decimal("-2.00")
        )
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=10.0, incoming_dpr=10.0, source_label="test")

        report = evaluate_capability(capability, context=context, reference=reference)

        bridge_rows = [v for v in report.valuations if v.kind == _KIND_CHECK_BRIDGE]
        self.assertEqual(len(bridge_rows), 1)
        self.assertLess(bridge_rows[0].value, 0.0)

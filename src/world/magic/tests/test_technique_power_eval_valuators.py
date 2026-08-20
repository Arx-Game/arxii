"""Tests for the technique combat-power evaluator's remaining valuators (#3279 Task 2).

Covers the buff/control/mitigation/heal/dispel/capability valuators Task 1 left
unimplemented: the team-damage-percent buff lane, the technique-level hard-control
estimate, the mitigation PARSE (regression-tested against the real shipped Defend
content — the plan's "key regression tripwire"), treatment healing (capped),
dispel/capability-grant zero-valued rows, and the UNPRICEABLE fallback for an
unrecognized protective family. The damage valuator + power/anima plumbing are
covered by ``test_technique_power_eval.py`` (Task 1) and are not repeated here.
"""

from __future__ import annotations

from django.test import TestCase

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
)
from world.combat.defend_content import DEFEND_PASSIVE_NAME, ensure_defend_content
from world.conditions.factories import (
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
    TreatmentTemplateFactory,
)
from world.magic.constants import (
    PCT_PER_POWER_TENTHS,
    TEAM_BUFF_LANE_CAP_PERCENT,
    TechniqueFunction,
)
from world.magic.factories import (
    TechniqueAppliedConditionFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
    TechniqueRemovedConditionFactory,
)
from world.magic.models.techniques import ConditionTargetKind, Technique, TechniqueTreatment
from world.magic.services.targeting import protective_magnitude
from world.magic.services.technique_power_eval import evaluate_technique
from world.magic.types.technique_power import EvalContext, ReferenceFrame, ValuationProvenance
from world.mechanics.factories import TeamDamagePercentTargetFactory
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckRankFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart

# PayloadValuation.kind values this suite filters on (a free string field, not a
# TextChoices — named constants here per the string-literal lint rule).
_KIND_BUFF = "buff"
_KIND_CONTROL = "control"
_KIND_MITIGATION = "mitigation"
_KIND_HEAL = "heal"
_KIND_DISPEL = "dispel"
_KIND_CAPABILITY = "capability"


class TechniquePowerEvalValuatorTestCase(TestCase):
    """Shared even-split SL1/SL3 matchup chart, mirroring Task 1's test setup."""

    @classmethod
    def setUpTestData(cls) -> None:
        # rank=0/min_points=0 puts EvalContext's default roller_points=25 and
        # target_difficulty=25 at the same rank -> rank_difference=0.
        CheckRankFactory(rank=0, min_points=0)

        cls.sl1 = CheckOutcomeFactory(name="Partial", success_level=1)
        cls.sl3 = CheckOutcomeFactory(name="Full", success_level=3)
        chart = ResultChartFactory(rank_difference=0, name="Even")
        ResultChartOutcomeFactory(chart=chart, outcome=cls.sl1, min_roll=1, max_roll=50)
        ResultChartOutcomeFactory(chart=chart, outcome=cls.sl3, min_roll=51, max_roll=100)

        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=1)

    def setUp(self) -> None:
        # ResultChart._chart_cache is a process-level dict, not transaction-scoped.
        ResultChart.clear_cache()

    def _technique(self, **kwargs) -> Technique:
        kwargs.setdefault("intensity", 4)
        kwargs.setdefault("damage_profile", False)
        return TechniqueFactory(**kwargs)


class TeamDamagePercentLaneTests(TechniquePowerEvalValuatorTestCase):
    """1a: the bounded team-damage-percent buff lane (#3279)."""

    def test_ally_buff_matches_hand_computed_percent_x_outgoing_dpr_x_duration(self) -> None:
        technique = self._technique(intensity=40)
        condition = ConditionTemplateFactory(default_duration_value=3)
        ConditionModifierEffectFactory(
            condition=condition,
            modifier_target=TeamDamagePercentTargetFactory(),
            scales_with_severity=True,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        context = EvalContext(level=10)
        reference = ReferenceFrame(outgoing_dpr=20.0, incoming_dpr=15.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        # Hand-computed: raw = power * PCT_PER_POWER_TENTHS / 10 / level; clamp 1..cap.
        raw = technique.intensity * PCT_PER_POWER_TENTHS / 10 / context.level
        percent = max(1, min(TEAM_BUFF_LANE_CAP_PERCENT, round(raw)))
        # duration is constant (base_duration_rounds=None -> condition default, no
        # power/SL scaling authored) across both bands, whose probabilities sum to 1.
        expected_duration = condition.default_duration_value
        expected_value = (percent / 100.0) * reference.outgoing_dpr * expected_duration

        buff_rows = [v for v in report.valuations if v.kind == _KIND_BUFF]
        self.assertEqual(len(buff_rows), 1)
        self.assertAlmostEqual(buff_rows[0].value, expected_value, places=6)
        self.assertEqual(buff_rows[0].provenance, ValuationProvenance.FORMULA)


class HardControlTests(TechniquePowerEvalValuatorTestCase):
    """2b: HOLD/FEAR/DISTRACTION hard-control estimate, once per technique (#3279)."""

    def test_hold_tag_values_expected_duration_x_incoming_dpr(self) -> None:
        technique = self._technique(intensity=5)
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.HOLD)
        condition = ConditionTemplateFactory(default_duration_value=4)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ENEMY,
            minimum_success_level=1,
        )
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=10.0, incoming_dpr=12.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        control_rows = [v for v in report.valuations if v.kind == _KIND_CONTROL]
        self.assertEqual(len(control_rows), 1)
        expected_value = condition.default_duration_value * reference.incoming_dpr
        self.assertAlmostEqual(control_rows[0].value, expected_value, places=6)
        self.assertEqual(control_rows[0].provenance, ValuationProvenance.ESTIMATE)

        # The underlying ENEMY row itself carries no DoT/modifier -> UNPRICEABLE,
        # separate from (in addition to) the technique-level control row.
        unpriceable_rows = [
            v for v in report.valuations if v.provenance == ValuationProvenance.UNPRICEABLE
        ]
        self.assertEqual(len(unpriceable_rows), 1)

    def test_no_control_row_without_function_tag(self) -> None:
        technique = self._technique(intensity=5)
        condition = ConditionTemplateFactory(default_duration_value=4)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ENEMY,
            minimum_success_level=1,
        )
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=10.0, incoming_dpr=12.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        self.assertFalse([v for v in report.valuations if v.kind == _KIND_CONTROL])


class MitigationParseTests(TechniquePowerEvalValuatorTestCase):
    """3: mitigation PARSE, regression-tested against the shipped Defend content."""

    def test_defend_content_parses_to_multiply_half_regression(self) -> None:
        """THE key regression tripwire: shipped Defend content must parse as 0.5x."""
        ensure_defend_content()
        technique = Technique.objects.get(name=DEFEND_PASSIVE_NAME)
        row = technique.condition_applications.get()

        magnitude = protective_magnitude(row.condition)

        self.assertIsNotNone(magnitude)
        self.assertEqual(magnitude.mode, "multiply")
        self.assertEqual(magnitude.factor, 0.5)

    def test_defend_content_values_as_50_percent_mitigation(self) -> None:
        ensure_defend_content()
        technique = Technique.objects.get(name=DEFEND_PASSIVE_NAME)
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=30.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        mitigation_rows = [v for v in report.valuations if v.kind == _KIND_MITIGATION]
        self.assertEqual(len(mitigation_rows), 1)
        self.assertEqual(mitigation_rows[0].provenance, ValuationProvenance.PARSED)
        # Shielded's default_duration_value=1, no power/SL scaling authored -> duration
        # is constant 1 across both bands, whose probabilities sum to 1.
        expected_value = 0.5 * reference.incoming_dpr * 1
        self.assertAlmostEqual(mitigation_rows[0].value, expected_value, places=6)
        # Defend carries no damage profile, so baseline_de is exactly the mitigation.
        self.assertAlmostEqual(report.baseline_de, expected_value, places=6)

    def test_unrecognized_protective_family_is_unpriceable(self) -> None:
        condition = ConditionTemplateFactory()
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.magic.services.effect_handlers.absorb_pool",
            parameters={},
        )
        trigger = TriggerDefinitionFactory(flow_definition=flow, event_name=EventName.EXAMINED)
        condition.reactive_triggers.add(trigger)

        self.assertIsNone(protective_magnitude(condition))

        technique = self._technique(intensity=4)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=1,
        )
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=10.0, incoming_dpr=10.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        matching = [v for v in report.valuations if v.label == condition.name]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].provenance, ValuationProvenance.UNPRICEABLE)
        self.assertEqual(matching[0].value, 0.0)


class DispelAndCapabilityGrantTests(TechniquePowerEvalValuatorTestCase):
    """5 + 6: dispel is never priced; capability grants are explicitly inert."""

    def test_dispel_row_is_unpriced_and_names_removed_conditions(self) -> None:
        technique = self._technique(intensity=3)
        removed = ConditionTemplateFactory(name="Charmed")
        TechniqueRemovedConditionFactory(technique=technique, condition=removed)
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=1.0, incoming_dpr=1.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        dispel_rows = [v for v in report.valuations if v.kind == _KIND_DISPEL]
        self.assertEqual(len(dispel_rows), 1)
        self.assertEqual(dispel_rows[0].value, 0.0)
        self.assertEqual(dispel_rows[0].provenance, ValuationProvenance.UNPRICED_DISPEL)
        self.assertIn("Charmed", dispel_rows[0].detail)

    def test_capability_grant_is_inert_payload(self) -> None:
        technique = self._technique(intensity=3)
        TechniqueCapabilityGrantFactory(technique=technique)
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=1.0, incoming_dpr=1.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        capability_rows = [v for v in report.valuations if v.kind == _KIND_CAPABILITY]
        self.assertEqual(len(capability_rows), 1)
        self.assertEqual(capability_rows[0].value, 0.0)
        self.assertEqual(capability_rows[0].provenance, ValuationProvenance.INERT_PAYLOAD)


class TreatmentHealingTests(TechniquePowerEvalValuatorTestCase):
    """4: treatment healing, capped at reference.incoming_dpr."""

    def test_treatment_healing_is_capped_at_incoming_dpr(self) -> None:
        technique = self._technique(intensity=5)
        treatment_template = TreatmentTemplateFactory(
            mend_on_crit=10, mend_on_success=6, mend_on_partial=2
        )
        TechniqueTreatment.objects.create(
            technique=technique,
            treatment_template=treatment_template,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=5.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        # Uncapped E[heal] = 0.5*mend_on_partial(sl1) + 0.5*mend_on_crit(sl3) = 1 + 5 = 6.
        # Capped at reference.incoming_dpr = 5.0.
        heal_rows = [v for v in report.valuations if v.kind == _KIND_HEAL]
        self.assertEqual(len(heal_rows), 1)
        self.assertEqual(heal_rows[0].value, 5.0)
        self.assertEqual(heal_rows[0].provenance, ValuationProvenance.FORMULA)

    def test_treatment_healing_uncapped_below_incoming_dpr(self) -> None:
        technique = self._technique(intensity=5)
        treatment_template = TreatmentTemplateFactory(
            mend_on_crit=10, mend_on_success=6, mend_on_partial=2
        )
        TechniqueTreatment.objects.create(
            technique=technique,
            treatment_template=treatment_template,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        context = EvalContext()
        reference = ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=100.0, source_label="test")

        report = evaluate_technique(technique, context, reference)

        heal_rows = [v for v in report.valuations if v.kind == _KIND_HEAL]
        self.assertEqual(len(heal_rows), 1)
        self.assertAlmostEqual(heal_rows[0].value, 6.0, places=6)

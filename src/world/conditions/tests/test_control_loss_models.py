"""Compulsion and control-loss trigger models, constraints and band validators (#4802)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.conditions.constants import CompulsionResult, ControlLossFiresOn
from world.conditions.control_loss_bands import (
    validate_compulsion_bands,
    validate_control_loss_bands,
)
from world.conditions.factories import (
    CompulsionFactory,
    CompulsionResistBandFactory,
    ConditionCategoryFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    ControlLossBandFactory,
    ControlLossTriggerFactory,
)
from world.traits.factories import CheckOutcomeFactory


class CompulsionModelTests(TestCase):
    def test_compulsion_requires_alters_behavior_category(self) -> None:
        plain = ConditionTemplateFactory(
            category=ConditionCategoryFactory(name="Plain", alters_behavior=False)
        )
        compulsion = CompulsionFactory.build(condition=plain)
        with self.assertRaises(ValidationError) as ctx:
            compulsion.full_clean(exclude=["check_type"])
        self.assertIn("condition", ctx.exception.message_dict)

    def test_compulsion_accepts_alters_behavior_category(self) -> None:
        CompulsionFactory().full_clean()


class ControlLossTriggerTests(TestCase):
    def test_trigger_kind_columns_enforced(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            stage = ConditionStageFactory()
            ControlLossTriggerFactory(
                vulnerability=stage.condition,
                fires_on=ControlLossFiresOn.WOUND_THRESHOLD,
                health_below_percent=50,
                stage=stage,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ControlLossTriggerFactory(fires_on=ControlLossFiresOn.CONDITION_STAGE)

    def test_valid_wound_and_stage_triggers_save(self) -> None:
        ControlLossTriggerFactory(wound=True)
        ControlLossTriggerFactory(staged=True)
        ControlLossTriggerFactory()

    def test_trigger_stage_must_belong_to_vulnerability(self) -> None:
        stage = ConditionStageFactory()
        other = ConditionTemplateFactory()
        trigger = ControlLossTriggerFactory.build(
            vulnerability=other, fires_on=ControlLossFiresOn.CONDITION_STAGE, stage=stage
        )
        with self.assertRaises(ValidationError) as ctx:
            trigger.clean()
        self.assertIn("stage", ctx.exception.message_dict)

    def test_forces_form_only_on_moon_pull(self) -> None:
        wound = ControlLossTriggerFactory(wound=True)
        band = ControlLossBandFactory.build(
            trigger=wound, outcome=CheckOutcomeFactory(success_level=1), forces_form=True
        )
        with self.assertRaises(ValidationError):
            band.clean()


class BandValidatorTests(TestCase):
    def test_validate_compulsion_bands_rejects_better_outcome_with_worse_result(self) -> None:
        compulsion = CompulsionFactory()
        worse = CompulsionResistBandFactory.build(
            compulsion=compulsion,
            outcome=CheckOutcomeFactory(name="Fail", success_level=-1),
            result=CompulsionResult.ACTS_STRAINED,
        )
        better = CompulsionResistBandFactory.build(
            compulsion=compulsion,
            outcome=CheckOutcomeFactory(name="Win", success_level=1),
            result=CompulsionResult.COMPULSION_ACTS,
        )
        self.assertEqual(len(validate_compulsion_bands([worse, better])), 1)
        better.result = CompulsionResult.ACTS_FREELY
        self.assertEqual(validate_compulsion_bands([worse, better]), [])

    def test_validate_control_loss_bands_rejects_better_outcome_with_more_severity(self) -> None:
        trigger = ControlLossTriggerFactory()
        worse = ControlLossBandFactory.build(
            trigger=trigger,
            outcome=CheckOutcomeFactory(name="Fail", success_level=-1),
            severity=1,
        )
        better = ControlLossBandFactory.build(
            trigger=trigger,
            outcome=CheckOutcomeFactory(name="Win", success_level=1),
            severity=3,
        )
        problems = validate_control_loss_bands([worse, better])
        self.assertEqual(len(problems), 1)
        self.assertIn("severity", problems[0])

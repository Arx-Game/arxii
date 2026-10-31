"""Compulsion and control-loss trigger models, constraints and band validators (#4802)."""

from types import SimpleNamespace

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from world.checks.factories import CheckTypeFactory
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
from world.conditions.models import ControlLossTrigger
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
        stage = ConditionStageFactory()
        vulnerability = ConditionTemplateFactory()
        check_type = CheckTypeFactory()
        wound_with_stage = ControlLossTriggerFactory.build(
            vulnerability=stage.condition,
            fires_on=ControlLossFiresOn.WOUND_THRESHOLD,
            health_below_percent=50,
            stage=stage,
            check_type=check_type,
        )
        stage_without_stage = ControlLossTriggerFactory.build(
            vulnerability=vulnerability,
            fires_on=ControlLossFiresOn.CONDITION_STAGE,
            check_type=check_type,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            wound_with_stage.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            stage_without_stage.save()

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


class ControlLossBandFormSetTests(TestCase):
    def test_formset_refuses_forced_form_on_non_moon_trigger(self) -> None:
        from world.conditions.admin import ControlLossBandInline

        request = RequestFactory().get("/")
        request.user = SimpleNamespace(has_perm=lambda _perm: True, is_active=True)
        outcome = CheckOutcomeFactory(success_level=1)
        trigger = ControlLossTrigger(
            fires_on=ControlLossFiresOn.WOUND_THRESHOLD, vulnerability=ConditionTemplateFactory()
        )  # unsaved, as on the add page
        formset_class = ControlLossBandInline(ControlLossTrigger, admin.site).get_formset(request)
        data = {
            "bands-TOTAL_FORMS": "1",
            "bands-INITIAL_FORMS": "0",
            "bands-MIN_NUM_FORMS": "0",
            "bands-MAX_NUM_FORMS": "1000",
            "bands-0-outcome": str(outcome.pk),
            "bands-0-intensity": "0",
            "bands-0-control_change": "0",
            "bands-0-severity": "1",
            "bands-0-duration_rounds": "1",
            "bands-0-forces_form": "on",
        }
        formset = formset_class(data, instance=trigger, prefix="bands")
        self.assertFalse(formset.is_valid())
        trigger.fires_on = ControlLossFiresOn.MOON_PULL
        moon = formset_class(data, instance=trigger, prefix="bands")
        self.assertTrue(moon.is_valid(), moon.errors)

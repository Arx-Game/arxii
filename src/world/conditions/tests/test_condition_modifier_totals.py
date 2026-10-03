"""condition_modifier_totals_by_sheet parity with get_condition_modifier_total (#4090)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import (
    condition_modifier_totals_by_sheet,
    get_condition_modifier_breakdown,
    get_condition_modifier_total,
    scaled_condition_effect_value,
)
from world.mechanics.factories import ModifierTargetFactory


class ConditionModifierTotalsBySheetTests(TestCase):
    def setUp(self) -> None:
        self.target = ModifierTargetFactory(name="TotalsTestTarget")
        self.other_target = ModifierTargetFactory(name="TotalsOtherTarget")
        self.sheet_a = CharacterSheetFactory()
        self.sheet_b = CharacterSheetFactory()
        self.template = ConditionTemplateFactory(name="TotalsTestCondition")
        ConditionModifierEffectFactory(
            condition=self.template,
            modifier_target=self.target,
            value=20,
            scales_with_severity=True,
        )

    def test_matches_single_sheet_total_and_scales_with_severity(self) -> None:
        ConditionInstanceFactory(target=self.sheet_a.character, condition=self.template, severity=2)
        totals = condition_modifier_totals_by_sheet([self.sheet_a.pk, self.sheet_b.pk], self.target)
        self.assertEqual(totals, {self.sheet_a.pk: 40})
        self.assertEqual(get_condition_modifier_total(self.sheet_a, self.target), 40)

    def test_two_conditions_on_one_target_sum(self) -> None:
        second = ConditionTemplateFactory(name="TotalsSecondCondition")
        ConditionModifierEffectFactory(condition=second, modifier_target=self.target, value=15)
        ConditionInstanceFactory(target=self.sheet_a.character, condition=self.template)
        ConditionInstanceFactory(target=self.sheet_a.character, condition=second)
        totals = condition_modifier_totals_by_sheet([self.sheet_a.pk], self.target)
        self.assertEqual(totals[self.sheet_a.pk], 35)

    def test_other_target_does_not_count(self) -> None:
        ConditionInstanceFactory(target=self.sheet_a.character, condition=self.template)
        totals = condition_modifier_totals_by_sheet([self.sheet_a.pk], self.other_target)
        self.assertEqual(totals, {})

    def test_suppressed_and_expired_instances_do_not_count(self) -> None:
        ConditionInstanceFactory(
            target=self.sheet_a.character, condition=self.template, is_suppressed=True
        )
        timed = ConditionTemplateFactory(
            name="TotalsTimedCondition", default_duration_type=DurationType.INGAME_TIME
        )
        ConditionModifierEffectFactory(condition=timed, modifier_target=self.target, value=30)
        ConditionInstanceFactory(
            target=self.sheet_b.character,
            condition=timed,
            expires_at=timezone.now() - timedelta(minutes=5),
        )
        totals = condition_modifier_totals_by_sheet([self.sheet_a.pk, self.sheet_b.pk], self.target)
        self.assertEqual(totals, {})

    def test_stage_effect_counts_only_for_current_stage(self) -> None:
        staged = ConditionTemplateFactory(name="TotalsStagedCondition", has_progression=True)
        stage_one = ConditionStageFactory(
            condition=staged, stage_order=1, severity_multiplier=Decimal("1.00")
        )
        stage_two = ConditionStageFactory(
            condition=staged, stage_order=2, severity_multiplier=Decimal("1.00")
        )
        ConditionModifierEffectFactory(
            condition=None, stage=stage_one, modifier_target=self.target, value=20
        )
        ConditionModifierEffectFactory(
            condition=None, stage=stage_two, modifier_target=self.target, value=70
        )
        ConditionInstanceFactory(
            target=self.sheet_a.character, condition=staged, current_stage=stage_two
        )
        totals = condition_modifier_totals_by_sheet([self.sheet_a.pk], self.target)
        self.assertEqual(totals[self.sheet_a.pk], 70)
        self.assertEqual(get_condition_modifier_total(self.sheet_a, self.target), 70)

    def test_query_count_is_fixed(self) -> None:
        for _ in range(3):
            sheet = CharacterSheetFactory()
            ConditionInstanceFactory(target=sheet.character, condition=self.template)
        ids = list(CharacterSheet.objects.values_list("pk", flat=True))
        with self.assertNumQueries(2):
            condition_modifier_totals_by_sheet(ids, self.target)

    def test_empty_input_runs_no_query(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(condition_modifier_totals_by_sheet([], self.target), {})

    def test_read_does_not_sweep_expired_ingame_time_instance(self) -> None:
        """A pure read must never tear down an expired row (F2) — that's a writer's job."""
        timed = ConditionTemplateFactory(
            name="TotalsExpirySweepCondition", default_duration_type=DurationType.INGAME_TIME
        )
        ConditionModifierEffectFactory(condition=timed, modifier_target=self.target, value=30)
        expired = ConditionInstanceFactory(
            target=self.sheet_b.character,
            condition=timed,
            expires_at=timezone.now() - timedelta(minutes=5),
        )
        condition_modifier_totals_by_sheet([self.sheet_b.pk], self.target)
        self.assertTrue(ConditionInstance.objects.filter(pk=expired.pk).exists())

    def test_breakdown_and_total_use_scaled_effect_value_consistently(self) -> None:
        """Parity for the refactor: get_condition_modifier_total and
        get_condition_modifier_breakdown must keep agreeing with
        scaled_condition_effect_value now that both call through it (#4090)."""
        staged = ConditionTemplateFactory(name="TotalsParityStagedCondition", has_progression=True)
        stage = ConditionStageFactory(
            condition=staged, stage_order=1, severity_multiplier=Decimal("2.50")
        )
        stage_effect = ConditionModifierEffectFactory(
            condition=None, stage=stage, modifier_target=self.target, value=10
        )
        severity_instance = ConditionInstanceFactory(
            target=self.sheet_a.character, condition=self.template, severity=3
        )
        severity_effect = self.template.conditionmodifiereffect_set.get(modifier_target=self.target)
        staged_instance = ConditionInstanceFactory(
            target=self.sheet_a.character, condition=staged, current_stage=stage
        )

        self.assertEqual(scaled_condition_effect_value(severity_effect, severity_instance), 60)
        self.assertEqual(scaled_condition_effect_value(stage_effect, staged_instance), 25)

        total = get_condition_modifier_total(self.sheet_a, self.target)
        breakdown = get_condition_modifier_breakdown(self.sheet_a, self.target)
        self.assertEqual(total, 85)
        self.assertEqual(sum(value for _, value in breakdown), total)

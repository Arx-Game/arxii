"""Tests for settle_round_effects (#4120)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.conditions.constants import DurationType, StackBehavior
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import (
    _ApplyConditionParams,
    _handle_refresh,
    _handle_stacking,
    get_settle_config,
    settle_round_effects,
    settled_effects_tick,
)
from world.conditions.types import InteractionResult


class SettleRoundEffectsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rounds_template = ConditionTemplateFactory(
            name="Settle Poison", default_duration_type=DurationType.ROUNDS
        )
        cls.scene_template = ConditionTemplateFactory(
            name="Settle Scene", default_duration_type=DurationType.SCENE
        )

    def test_rounds_row_converts_to_expiry(self):
        inst = ConditionInstanceFactory(condition=self.rounds_template, rounds_remaining=4)
        cfg = get_settle_config()
        before = timezone.now()
        settle_round_effects([inst.target])
        inst.refresh_from_db()
        self.assertIsNone(inst.rounds_remaining)
        self.assertGreaterEqual(
            inst.expires_at, before + timedelta(seconds=4 * cfg.settled_seconds_per_round)
        )
        self.assertIsNotNone(inst.last_settled_tick_at)

    def test_second_run_does_not_extend(self):
        inst = ConditionInstanceFactory(condition=self.rounds_template, rounds_remaining=2)
        settle_round_effects([inst.target])
        inst.refresh_from_db()
        first = inst.expires_at
        self.assertEqual(settle_round_effects([inst.target]), [])
        inst.refresh_from_db()
        self.assertEqual(inst.expires_at, first)

    def test_non_rounds_rows_untouched(self):
        inst = ConditionInstanceFactory(condition=self.scene_template, rounds_remaining=None)
        settle_round_effects([inst.target])
        inst.refresh_from_db()
        self.assertIsNone(inst.expires_at)

    def test_zero_rounds_settles_to_now(self):
        inst = ConditionInstanceFactory(condition=self.rounds_template, rounds_remaining=0)
        settle_round_effects([inst.target])
        inst.refresh_from_db()
        self.assertLessEqual(inst.expires_at, timezone.now())

    def test_resolved_rows_skipped(self):
        inst = ConditionInstanceFactory(
            condition=self.rounds_template, rounds_remaining=3, resolved_at=timezone.now()
        )
        self.assertEqual(settle_round_effects([inst.target]), [])
        inst.refresh_from_db()
        self.assertEqual(inst.rounds_remaining, 3)


class ReapplyConvertedRowTests(TestCase):
    """Re-applying a converted row returns it to round-based accounting (#4120).

    Drives the stacking and refresh handlers directly: ``apply_condition`` reaches
    ConditionStage lookups that use DISTINCT ON, which SQLite cannot run.
    """

    @classmethod
    def setUpTestData(cls):
        cls.stacking = ConditionTemplateFactory(
            name="Reapply Stack",
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
            is_stackable=True,
            stack_behavior=StackBehavior.DURATION,
        )
        cls.refreshing = ConditionTemplateFactory(
            name="Reapply Refresh",
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
            is_stackable=False,
        )

    def _converted(self, template):
        inst = ConditionInstanceFactory(condition=template, rounds_remaining=4)
        settle_round_effects([inst.target])
        inst.refresh_from_db()
        inst.lapse_warned_at = timezone.now()
        inst.save(update_fields=["lapse_warned_at"])
        return inst

    def _assert_round_based(self, inst, rounds):
        inst.refresh_from_db()
        self.assertEqual(inst.rounds_remaining, rounds)
        self.assertIsNone(inst.expires_at)
        self.assertIsNone(inst.last_settled_tick_at)
        self.assertIsNone(inst.lapse_warned_at)
        summary = settled_effects_tick()
        self.assertEqual((summary.removed, summary.ticked), (0, 0))
        self.assertTrue(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_stacking_returns_converted_row_to_rounds(self):
        inst = self._converted(self.stacking)
        params = _ApplyConditionParams(target=inst.target, duration_rounds=5)
        _handle_stacking(inst, self.stacking, params, InteractionResult())
        self._assert_round_based(inst, 5)

    def test_refresh_returns_converted_row_to_rounds(self):
        inst = self._converted(self.refreshing)
        params = _ApplyConditionParams(target=inst.target, duration_rounds=6)
        _handle_refresh(inst, self.refreshing, params, InteractionResult())
        self._assert_round_based(inst, 6)

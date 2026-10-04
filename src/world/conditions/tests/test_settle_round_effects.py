"""Tests for settle_round_effects (#4120)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.services import get_settle_config, settle_round_effects


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

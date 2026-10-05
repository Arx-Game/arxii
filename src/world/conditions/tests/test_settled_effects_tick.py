from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import Allegiance, DurationType
from world.conditions.factories import (
    ConditionDamageOverTimeFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import settled_effects_tick
from world.vitals.constants import KNOCKOUT_HEALTH_THRESHOLD, CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory

ROUND_SECONDS = 300  # SettleConfig default


class SettledEffectsTickTests(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.now = timezone.now()

    def _converted(self, *, damage=10, ticked_ago=301, expires_in=3000, **template_kwargs):
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, **template_kwargs
        )
        if damage:
            ConditionDamageOverTimeFactory(condition=template, base_damage=damage)
        return ConditionInstanceFactory(
            target=self.sheet.character,
            condition=template,
            rounds_remaining=None,
            expires_at=self.now + timedelta(seconds=expires_in),
            last_settled_tick_at=self.now - timedelta(seconds=ticked_ago),
        )

    def _health(self):
        self.vitals.refresh_from_db()
        return self.vitals.health

    def test_dot_ticks_once_when_period_elapsed(self):
        inst = self._converted(damage=10)
        summary = settled_effects_tick()
        self.assertEqual(self._health(), 90)
        self.assertEqual(summary.ticked, 1)
        inst.refresh_from_db()
        self.assertEqual(
            inst.last_settled_tick_at, self.now - timedelta(seconds=301) + timedelta(seconds=300)
        )

    def test_dot_ticks_clamped_above_knockout_even_when_target_would_die(self):
        self._converted(damage=10_000)
        settled_effects_tick()
        floor = int(KNOCKOUT_HEALTH_THRESHOLD * self.vitals.max_health) + 1
        self.assertEqual(self._health(), floor)
        self.assertEqual(self.vitals.life_state, CharacterLifeState.ALIVE)

    def test_no_tick_before_period_elapses(self):
        self._converted(damage=10, ticked_ago=10)
        settled_effects_tick()
        self.assertEqual(self._health(), 100)

    def test_expired_row_removed(self):
        inst = self._converted(damage=10, expires_in=-5)
        summary = settled_effects_tick()
        self.assertFalse(ConditionInstance.objects.filter(pk=inst.pk).exists())
        self.assertEqual(summary.removed, 1)
        self.assertEqual(self._health(), 100)

    def test_expired_row_goes_through_remove_condition(self):
        self._converted(damage=0, expires_in=-5)
        with patch("world.conditions.services.remove_condition", return_value=True) as removed:
            settled_effects_tick()
        self.assertEqual(removed.call_args.kwargs, {"include_suppressed": True})

    def test_sheetless_target_converted_row_expires_without_damage(self):
        inst = ConditionInstanceFactory(
            condition=ConditionTemplateFactory(default_duration_type=DurationType.ROUNDS),
            rounds_remaining=None,
            expires_at=self.now - timedelta(seconds=5),
            last_settled_tick_at=self.now - timedelta(seconds=400),
        )
        settled_effects_tick()
        self.assertFalse(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_sheetless_live_row_is_left_alone(self):
        template = ConditionTemplateFactory(default_duration_type=DurationType.ROUNDS)
        ConditionDamageOverTimeFactory(condition=template, base_damage=10)
        inst = ConditionInstanceFactory(
            condition=template,
            rounds_remaining=None,
            expires_at=self.now + timedelta(seconds=900),
            last_settled_tick_at=self.now - timedelta(seconds=400),
        )
        settled_effects_tick()
        self.assertTrue(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_row_in_active_round_context_is_skipped(self):
        inst = self._converted(damage=10)
        with patch("actions.round_context.get_active_round_context", return_value=object()):
            summary = settled_effects_tick()
        self.assertEqual(self._health(), 100)
        self.assertEqual(summary.active_round_skipped, 1)
        inst.refresh_from_db()
        self.assertEqual(inst.last_settled_tick_at, self.now - timedelta(seconds=301))

    def test_allegiance_row_not_removed_here(self):
        inst = self._converted(damage=0, expires_in=-5, sets_allegiance=Allegiance.ALLY_OF_CASTER)
        settled_effects_tick()
        self.assertTrue(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_unconverted_rounds_row_untouched(self):
        template = ConditionTemplateFactory(default_duration_type=DurationType.ROUNDS)
        ConditionDamageOverTimeFactory(condition=template, base_damage=10)
        ConditionInstanceFactory(
            target=self.sheet.character, condition=template, rounds_remaining=3
        )
        settled_effects_tick()
        self.assertEqual(self._health(), 100)

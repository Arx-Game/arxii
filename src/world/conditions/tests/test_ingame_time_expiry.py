"""Tests for in-game-time (IC-calendar) condition expiry (#2537)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from evennia.utils.test_resources import EvenniaTestCase


class ComputeIngameTimeExpiresTests(TestCase):
    """Unit tests for the _compute_ingame_time_expires helper."""

    def test_computes_expires_at_from_ic_hours_and_ratio(self):
        """24 IC hours at ratio 3.0 → expires ~8 real hours from now."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.services import _compute_ingame_time_expires
        from world.game_clock.models import GameClock

        clock = GameClock.get_active()
        if clock is None:
            clock = GameClock.objects.create(
                anchor_real_time=timezone.now(),
                anchor_ic_time=timezone.now(),
                time_ratio=3.0,
            )
        else:
            clock.time_ratio = 3.0
            clock.save()

        tmpl = ConditionTemplateFactory(
            name="Test Poison",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=24,
        )

        before = timezone.now()
        expires_at = _compute_ingame_time_expires(tmpl)
        after = timezone.now()

        self.assertIsNotNone(expires_at)
        # 24 IC hours / 3.0 ratio = 8 real hours
        expected_min = before + timedelta(hours=8)
        expected_max = after + timedelta(hours=8)
        self.assertGreaterEqual(expires_at, expected_min)
        self.assertLessEqual(expires_at, expected_max)

    def test_returns_none_for_zero_duration(self):
        """A zero default_duration_value → None (never expires)."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.services import _compute_ingame_time_expires

        tmpl = ConditionTemplateFactory(
            name="Zero Duration",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=0,
        )
        self.assertIsNone(_compute_ingame_time_expires(tmpl))

    def test_returns_none_when_no_clock(self):
        """No game clock → None (condition won't expire by IC time)."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.services import _compute_ingame_time_expires
        from world.game_clock.models import GameClock

        # Delete any existing clock
        GameClock.objects.all().delete()

        tmpl = ConditionTemplateFactory(
            name="No Clock Poison",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=24,
        )
        self.assertIsNone(_compute_ingame_time_expires(tmpl))


class ApplyIngameTimeConditionTests(EvenniaTestCase):
    """Tests that apply_condition sets expires_at for INGAME_TIME conditions."""

    def test_apply_sets_expires_at(self):
        """Applying an INGAME_TIME condition stores a computed expires_at."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionTemplateFactory,
        )
        from world.conditions.services import apply_condition
        from world.game_clock.models import GameClock
        from world.scenes.factories import PersonaFactory

        clock = GameClock.get_active()
        if clock is None:
            clock = GameClock.objects.create(
                anchor_real_time=timezone.now(),
                anchor_ic_time=timezone.now(),
                time_ratio=3.0,
            )
        else:
            clock.time_ratio = 3.0
            clock.save()

        persona = PersonaFactory()
        target = persona.character_sheet.character
        tmpl = ConditionTemplateFactory(
            name="Test Curse",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=12,  # 12 IC hours = 4 real hours at 3:1
        )

        before = timezone.now()
        result = apply_condition(target, tmpl, severity=1)
        after = timezone.now()

        self.assertTrue(result.success)
        self.assertIsNotNone(result.instance.expires_at)
        # 12 IC hours / 3.0 = 4 real hours
        expected_min = before + timedelta(hours=4)
        expected_max = after + timedelta(hours=4)
        self.assertGreaterEqual(result.instance.expires_at, expected_min)
        self.assertLessEqual(result.instance.expires_at, expected_max)

    def test_apply_non_ingame_time_has_no_expires_at(self):
        """A ROUNDS condition gets expires_at=None."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.services import apply_condition
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        target = persona.character_sheet.character
        tmpl = ConditionTemplateFactory(
            name="Bleeding",
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
        )

        result = apply_condition(target, tmpl, severity=1)

        self.assertTrue(result.success)
        self.assertIsNone(result.instance.expires_at)

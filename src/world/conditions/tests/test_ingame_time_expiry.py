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


class LazyExpiryTests(EvenniaTestCase):
    """Tests for the lazy IC-time expiry check in get_active_conditions."""

    def test_expired_condition_removed_on_read(self):
        """An INGAME_TIME condition past its expires_at is removed when
        get_active_conditions is called."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.conditions.services import get_active_conditions
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        target = persona.character_sheet.character
        tmpl = ConditionTemplateFactory(
            name="Expired Poison",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=24,
        )
        # Set expires_at in the past
        inst = ConditionInstanceFactory(
            target=target,
            condition=tmpl,
            rounds_remaining=None,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        result = get_active_conditions(target)

        self.assertFalse(ConditionInstance.objects.filter(pk=inst.pk).exists())
        self.assertNotIn(inst, result)

    def test_non_expired_condition_survives_read(self):
        """An INGAME_TIME condition with a future expires_at survives."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.services import get_active_conditions
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        target = persona.character_sheet.character
        tmpl = ConditionTemplateFactory(
            name="Active Curse",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=24,
        )
        inst = ConditionInstanceFactory(
            target=target,
            condition=tmpl,
            rounds_remaining=None,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        result = get_active_conditions(target)

        self.assertIn(inst, result)

    def test_no_expires_at_conditions_not_touched(self):
        """Conditions with expires_at=None (ROUNDS, SCENE, etc.) are not
        affected by the lazy sweep."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.services import get_active_conditions
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        target = persona.character_sheet.character
        rounds_tmpl = ConditionTemplateFactory(
            name="Bleeding",
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
        )
        inst = ConditionInstanceFactory(
            target=target,
            condition=rounds_tmpl,
            rounds_remaining=3,
            expires_at=None,
        )

        result = get_active_conditions(target)

        self.assertIn(inst, result)

    def test_non_ingame_time_with_past_expires_at_not_swept(self):
        """A non-INGAME_TIME condition (e.g. UNTIL_CURED) with a past
        expires_at is NOT removed by the lazy sweep — the expires_at field
        is also used by the wake-arc system as a force-wake backstop (#2287),
        so only INGAME_TIME conditions are eligible for IC-time expiry."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.services import get_active_conditions
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        target = persona.character_sheet.character
        # UNTIL_CURED condition (like Unconscious) with a past expires_at
        # — the wake system uses this as a force-wake deadline
        until_cured_tmpl = ConditionTemplateFactory(
            name="Unconscious-like",
            default_duration_type=DurationType.UNTIL_CURED,
            default_duration_value=0,
        )
        inst = ConditionInstanceFactory(
            target=target,
            condition=until_cured_tmpl,
            rounds_remaining=None,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        result = get_active_conditions(target)

        # The condition survives — the lazy sweep only targets INGAME_TIME
        self.assertIn(inst, result)

    def test_afk_safety_condition_lingers_until_read(self):
        """An expired INGAME_TIME condition lingers in DB until
        get_active_conditions is called (not swept by time alone)."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        target = persona.character_sheet.character
        tmpl = ConditionTemplateFactory(
            name="Lingering Poison",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=24,
        )
        inst = ConditionInstanceFactory(
            target=target,
            condition=tmpl,
            rounds_remaining=None,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        # Without calling get_active_conditions, the instance still exists
        self.assertTrue(ConditionInstance.objects.filter(pk=inst.pk).exists())


class RefreshIngameTimeConditionTests(EvenniaTestCase):
    """Tests that re-applying an INGAME_TIME condition recomputes expires_at."""

    def test_refresh_recomputes_expires_at(self):
        """Re-applying an INGAME_TIME condition resets expires_at from now."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import ConditionTemplateFactory
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
            name="Refreshing Curse",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=24,  # 24 IC hours = 8 real hours
        )

        # First application
        result1 = apply_condition(target, tmpl, severity=1)
        original_expires = result1.instance.expires_at
        self.assertIsNotNone(original_expires)

        # Wait a moment, then re-apply (refresh)
        import time

        time.sleep(0.01)
        result2 = apply_condition(target, tmpl, severity=1)

        self.assertTrue(result2.success)
        self.assertIsNotNone(result2.instance.expires_at)
        # The refreshed expires_at should be later than the original
        self.assertGreater(result2.instance.expires_at, original_expires)

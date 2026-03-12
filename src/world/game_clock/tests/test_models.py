"""Tests for game clock models."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.game_clock.factories import GameClockFactory, GameClockHistoryFactory
from world.game_clock.models import GameClock


class GameClockTest(TestCase):
    """Tests for the GameClock model."""

    @classmethod
    def setUpTestData(cls) -> None:
        now = timezone.now()
        ic_start = now.replace(year=1, month=1, day=1, hour=0, minute=0, second=0)
        cls.clock = GameClockFactory(
            anchor_real_time=now,
            anchor_ic_time=ic_start,
            time_ratio=3.0,
        )
        cls.anchor_real = now
        cls.anchor_ic = ic_start

    def test_get_ic_now_at_anchor_returns_anchor_ic_time(self) -> None:
        """get_ic_now at the exact anchor real time returns anchor_ic_time."""
        result = self.clock.get_ic_now(real_now=self.anchor_real)
        self.assertEqual(result, self.anchor_ic)

    def test_get_ic_now_one_hour_later_with_ratio(self) -> None:
        """1 real hour later with ratio=3.0 returns 3 IC hours later."""
        one_hour_later = self.anchor_real + timedelta(hours=1)
        result = self.clock.get_ic_now(real_now=one_hour_later)
        expected = self.anchor_ic + timedelta(hours=3)
        self.assertEqual(result, expected)

    def test_get_ic_now_when_paused_returns_anchor(self) -> None:
        """When paused, get_ic_now returns anchor_ic_time regardless of elapsed time."""
        self.clock.paused = True
        try:
            far_future = self.anchor_real + timedelta(days=100)
            result = self.clock.get_ic_now(real_now=far_future)
            self.assertEqual(result, self.anchor_ic)
        finally:
            self.clock.paused = False

    def test_str_contains_game_clock(self) -> None:
        """__str__ includes 'GameClock'."""
        self.assertIn("GameClock", str(self.clock))

    def test_get_active_returns_clock(self) -> None:
        """get_active returns the singleton clock when it exists."""
        result = GameClock.get_active()
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.clock.pk)


class GameClockGetActiveEmptyTest(TestCase):
    """Test get_active when no GameClock exists."""

    def test_get_active_returns_none_when_empty(self) -> None:
        """get_active returns None when no GameClock exists."""
        self.assertIsNone(GameClock.get_active())


class GameClockHistoryTest(TestCase):
    """Tests for the GameClockHistory model."""

    @classmethod
    def setUpTestData(cls) -> None:
        now = timezone.now()
        cls.history = GameClockHistoryFactory(
            old_anchor_real_time=now,
            old_anchor_ic_time=now,
            old_time_ratio=3.0,
            new_anchor_real_time=now,
            new_anchor_ic_time=now,
            new_time_ratio=5.0,
            reason="Testing ratio change",
        )

    def test_str_contains_clock_change(self) -> None:
        """__str__ includes 'Clock change'."""
        self.assertIn("Clock change", str(self.history))

    def test_history_stores_reason(self) -> None:
        """History records store the reason for the change."""
        self.assertEqual(self.history.reason, "Testing ratio change")

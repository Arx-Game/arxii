"""Tests for game clock service functions."""

from datetime import UTC, datetime, timedelta

from django.test import TestCase

from world.game_clock.constants import Season, TimePhase
from world.game_clock.factories import GameClockFactory
from world.game_clock.services import (
    get_ic_date_for_real_time,
    get_ic_now,
    get_ic_phase,
    get_ic_season,
    get_light_level,
    get_real_time_for_ic_date,
)


class GetIcNowTests(TestCase):
    """Tests for get_ic_now service function."""

    def test_returns_ic_time_at_anchor(self) -> None:
        """At anchor_real_time, IC time should equal anchor_ic_time."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 6, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_ic_now(real_now=real_anchor)
        self.assertEqual(result, ic_anchor)

    def test_returns_none_when_no_clock(self) -> None:
        """Should return None when no GameClock exists."""
        result = get_ic_now()
        self.assertIsNone(result)

    def test_advances_over_time(self) -> None:
        """2 real hours at 3:1 ratio should yield 6 IC hours."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 6, 15, 0, 0, 0, tzinfo=UTC)
        GameClockFactory(
            anchor_real_time=real_anchor,
            anchor_ic_time=ic_anchor,
            time_ratio=3.0,
        )

        two_hours_later = real_anchor + timedelta(hours=2)
        result = get_ic_now(real_now=two_hours_later)
        expected = ic_anchor + timedelta(hours=6)
        self.assertEqual(result, expected)


class GetIcSeasonTests(TestCase):
    """Tests for get_ic_season service function."""

    def test_month_7_is_summer(self) -> None:
        """Month 7 (July) should be SUMMER."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 7, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_ic_season(real_now=real_anchor)
        self.assertEqual(result, Season.SUMMER)

    def test_month_1_is_winter(self) -> None:
        """Month 1 (January) should be WINTER."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 1, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_ic_season(real_now=real_anchor)
        self.assertEqual(result, Season.WINTER)

    def test_returns_none_when_no_clock(self) -> None:
        """Should return None when no GameClock exists."""
        result = get_ic_season()
        self.assertIsNone(result)


class GetIcPhaseTests(TestCase):
    """Tests for get_ic_phase service function."""

    def test_noon_in_summer_is_day(self) -> None:
        """Hour 12 in summer should be DAY."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 7, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_ic_phase(real_now=real_anchor)
        self.assertEqual(result, TimePhase.DAY)

    def test_midnight_is_night(self) -> None:
        """Hour 0 should be NIGHT regardless of season."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 7, 15, 0, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_ic_phase(real_now=real_anchor)
        self.assertEqual(result, TimePhase.NIGHT)

    def test_hour_5_in_winter_is_night(self) -> None:
        """Hour 5 in winter (dawn starts at 7.0) should be NIGHT."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 1, 15, 5, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_ic_phase(real_now=real_anchor)
        self.assertEqual(result, TimePhase.NIGHT)

    def test_hour_5_in_summer_is_dawn(self) -> None:
        """Hour 5 in summer (dawn starts at 4.5) should be DAWN."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 7, 15, 5, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_ic_phase(real_now=real_anchor)
        self.assertEqual(result, TimePhase.DAWN)

    def test_returns_none_when_no_clock(self) -> None:
        """Should return None when no GameClock exists."""
        result = get_ic_phase()
        self.assertIsNone(result)


class GetLightLevelTests(TestCase):
    """Tests for get_light_level service function."""

    def test_midday_high_light(self) -> None:
        """Midday should have light level > 0.8."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 7, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_light_level(real_now=real_anchor)
        self.assertIsNotNone(result)
        self.assertGreater(result, 0.8)

    def test_midnight_low_light(self) -> None:
        """Midnight should have light level < 0.2."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 7, 15, 0, 0, 0, tzinfo=UTC)
        GameClockFactory(anchor_real_time=real_anchor, anchor_ic_time=ic_anchor)

        result = get_light_level(real_now=real_anchor)
        self.assertIsNotNone(result)
        self.assertLess(result, 0.2)

    def test_returns_none_when_no_clock(self) -> None:
        """Should return None when no GameClock exists."""
        result = get_light_level()
        self.assertIsNone(result)


class DateConversionTests(TestCase):
    """Tests for IC/real time conversion functions."""

    def test_ic_to_real_roundtrip(self) -> None:
        """Converting IC→real→IC should return the original IC time (within 1s)."""
        real_anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ic_anchor = datetime(1, 6, 15, 12, 0, 0, tzinfo=UTC)
        GameClockFactory(
            anchor_real_time=real_anchor,
            anchor_ic_time=ic_anchor,
            time_ratio=3.0,
        )

        # Pick an IC time 10 IC days ahead of anchor
        target_ic = ic_anchor + timedelta(days=10)
        real_time = get_real_time_for_ic_date(target_ic)
        self.assertIsNotNone(real_time)

        roundtrip_ic = get_ic_date_for_real_time(real_time)
        self.assertIsNotNone(roundtrip_ic)

        diff = abs((roundtrip_ic - target_ic).total_seconds())
        self.assertLessEqual(diff, 1.0)

    def test_returns_none_when_no_clock(self) -> None:
        """Both conversion functions should return None when no clock exists."""
        real_dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        ic_dt = datetime(1, 6, 1, 12, 0, 0, tzinfo=UTC)

        self.assertIsNone(get_ic_date_for_real_time(real_dt))
        self.assertIsNone(get_real_time_for_ic_date(ic_dt))

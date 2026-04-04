"""Tests for the GameWeek system."""

from django.test import TestCase
from django.utils import timezone

from world.game_clock.models import GameSeason, GameWeek
from world.game_clock.week_services import (
    advance_game_week,
    get_current_game_week,
    start_new_season,
)


class GetCurrentGameWeekTest(TestCase):
    """Test get_current_game_week bootstrapping and retrieval."""

    def test_bootstraps_season_and_week_on_fresh_install(self) -> None:
        """First call creates Season 1, Week 1."""
        week = get_current_game_week()
        self.assertEqual(week.number, 1)
        self.assertTrue(week.is_current)
        self.assertIsNotNone(week.season)
        self.assertEqual(week.season.number, 1)

    def test_returns_existing_current_week(self) -> None:
        """Subsequent calls return the same week."""
        week1 = get_current_game_week()
        week2 = get_current_game_week()
        self.assertEqual(week1.pk, week2.pk)

    def test_only_one_current_week(self) -> None:
        """Only one week has is_current=True."""
        get_current_game_week()
        self.assertEqual(GameWeek.objects.filter(is_current=True).count(), 1)


class AdvanceGameWeekTest(TestCase):
    """Test advance_game_week rollover logic."""

    def test_advances_week_number(self) -> None:
        """advance_game_week creates week N+1."""
        get_current_game_week()  # Bootstrap week 1
        new_week = advance_game_week()
        self.assertEqual(new_week.number, 2)
        self.assertTrue(new_week.is_current)

    def test_closes_previous_week(self) -> None:
        """Previous week gets ended_at and is_current=False."""
        week1 = get_current_game_week()
        advance_game_week()
        week1.refresh_from_db()
        self.assertFalse(week1.is_current)
        self.assertIsNotNone(week1.ended_at)

    def test_preserves_season(self) -> None:
        """New week inherits the season from the previous week."""
        week1 = get_current_game_week()
        new_week = advance_game_week()
        self.assertEqual(new_week.season, week1.season)

    def test_multiple_advances(self) -> None:
        """Can advance multiple times."""
        get_current_game_week()
        advance_game_week()
        week3 = advance_game_week()
        self.assertEqual(week3.number, 3)
        self.assertEqual(GameWeek.objects.count(), 3)
        self.assertEqual(GameWeek.objects.filter(is_current=True).count(), 1)

    def test_only_one_current_after_advance(self) -> None:
        """After advance, exactly one week is current."""
        get_current_game_week()
        advance_game_week()
        self.assertEqual(GameWeek.objects.filter(is_current=True).count(), 1)


class StartNewSeasonTest(TestCase):
    """Test start_new_season."""

    def test_creates_new_season(self) -> None:
        """start_new_season creates a new GameSeason."""
        get_current_game_week()  # Bootstrap Season 1
        season2 = start_new_season("Season 2")
        self.assertEqual(season2.number, 2)
        self.assertEqual(season2.name, "Season 2")

    def test_next_advance_resets_week_to_1(self) -> None:
        """After starting a new season, the next advance creates Week 1."""
        get_current_game_week()  # S1 W1
        advance_game_week()  # S1 W2
        start_new_season("Season 2")
        new_week = advance_game_week()
        self.assertEqual(new_week.number, 1)
        self.assertEqual(new_week.season.name, "Season 2")


class GameWeekStrTest(TestCase):
    """Test string representations."""

    def test_str_with_season(self) -> None:
        season = GameSeason.objects.create(number=1, name="Season 1")
        week = GameWeek.objects.create(
            number=3, season=season, started_at=timezone.now(), is_current=True
        )
        self.assertEqual(str(week), "S1 Week 3")

    def test_season_str(self) -> None:
        season = GameSeason.objects.create(number=2, name="The Reckoning")
        self.assertEqual(str(season), "The Reckoning")

    def test_season_str_no_name(self) -> None:
        season = GameSeason.objects.create(number=3)
        self.assertEqual(str(season), "Season 3")

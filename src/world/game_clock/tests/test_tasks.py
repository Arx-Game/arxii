"""Tests for periodic batch task functions."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.game_clock.tasks import (
    batch_condition_expiration_cleanup,
    batch_form_expiration_cleanup,
    batch_journal_weekly_reset,
)


class BatchJournalWeeklyResetTests(TestCase):
    def test_resets_stale_trackers(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.journals.models import WeeklyJournalXP

        sheet = CharacterSheetFactory()
        tracker = WeeklyJournalXP.objects.create(
            character_sheet=sheet, posts_this_week=3, praised_this_week=True
        )
        tracker.week_reset_at = timezone.now() - timedelta(days=8)
        tracker.save(update_fields=["week_reset_at"])

        batch_journal_weekly_reset()

        tracker.refresh_from_db()
        self.assertEqual(tracker.posts_this_week, 0)
        self.assertFalse(tracker.praised_this_week)

    def test_skips_fresh_trackers(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.journals.models import WeeklyJournalXP

        sheet = CharacterSheetFactory()
        WeeklyJournalXP.objects.create(character_sheet=sheet, posts_this_week=2)

        batch_journal_weekly_reset()

        tracker = WeeklyJournalXP.objects.get(character_sheet=sheet)
        self.assertEqual(tracker.posts_this_week, 2)


class BatchFormExpirationTests(TestCase):
    def test_runs_without_error(self) -> None:
        batch_form_expiration_cleanup()


class BatchConditionExpirationTests(TestCase):
    def test_runs_without_error(self) -> None:
        batch_condition_expiration_cleanup()

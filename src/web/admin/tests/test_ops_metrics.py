"""Tests for Game Ops dashboard metrics (#1221 Task 7).

Covers zero-fill correctness, mint/sink/transfer classification, reports
open-count status logic, and the "one query per series" contract.
"""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.utils import timezone

from web.admin.tuning.metrics import (
    economy_series,
    level_distribution,
    money_supply,
    progression_series,
    reports_snapshot,
    story_series,
    story_snapshot,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.currency.models import CharacterPurse, OrganizationTreasury
from world.currency.services import get_or_create_purse, get_or_create_treasury, transfer
from world.gm.constants import GMTableStatus
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.factories import PlayerFeedbackFactory
from world.progression.factories import (
    CharacterXPTransactionFactory,
    DevelopmentTransactionFactory,
)
from world.progression.models import CharacterXPTransaction
from world.societies.factories import OrganizationFactory
from world.stories.constants import SessionRequestStatus
from world.stories.factories import SessionRequestFactory, StoryFactory
from world.stories.types import StoryStatus


def _this_monday() -> datetime.date:
    today = timezone.now().date()
    return today - datetime.timedelta(days=today.weekday())


class ProgressionSeriesTests(TestCase):
    """Zero-fill + "earned" filtering for `progression_series`."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.monday = _this_monday()
        cls.sheet = CharacterSheetFactory()

        # transaction_date is auto_now_add; backdate via .update() after
        # create (standard pattern in this repo, e.g.
        # world/progression/tests/test_random_scene_services.py).
        earn = CharacterXPTransactionFactory(character=cls.sheet, amount=100)
        CharacterXPTransaction.objects.filter(pk=earn.pk).update(transaction_date=timezone.now())

        # A negative (spend) transaction this week must NOT count as "earned".
        spend = CharacterXPTransactionFactory(character=cls.sheet, amount=-40)
        CharacterXPTransaction.objects.filter(pk=spend.pk).update(transaction_date=timezone.now())

    def test_zero_fill_for_week_with_no_rows(self) -> None:
        series = progression_series(weeks=8)
        xp_series = next(s for s in series if s.label == "XP earned")
        # Oldest week (7 weeks back) has no rows -> zero-filled, not omitted.
        assert xp_series.points[0].week_start == self.monday - datetime.timedelta(weeks=7)
        assert xp_series.points[0].value == 0.0
        assert len(xp_series.points) == 8

    def test_this_week_sums_only_positive_amounts(self) -> None:
        series = progression_series(weeks=8)
        xp_series = next(s for s in series if s.label == "XP earned")
        assert xp_series.points[-1].week_start == self.monday
        assert xp_series.points[-1].value == 100.0

    def test_development_points_and_level_ups_series_present(self) -> None:
        DevelopmentTransactionFactory(amount=25)
        series = progression_series(weeks=8)
        labels = {s.label for s in series}
        assert labels == {"XP earned", "Development points", "Level-ups"}

    def test_one_query_per_series(self) -> None:
        """3 series (XP, dev points, level-ups) -> exactly 3 aggregate queries."""
        with self.assertNumQueries(3):
            progression_series(weeks=8)


class WeeklyWindowBoundaryTests(TestCase):
    """Pins `_week_boundaries`'s Monday-anchored cutoff.

    The window filter is `transaction_date__date__gte=cutoff` where `cutoff`
    is the oldest tracked Monday — so a row dated 00:30 UTC on that Monday is
    inside the window (falls in the oldest bucket), while a row dated 23:30
    UTC the Sunday immediately before is outside it entirely (excluded by the
    query, not merely bucketed elsewhere).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        today = timezone.now().date()
        this_monday = today - datetime.timedelta(days=today.weekday())
        cls.oldest_monday = this_monday - datetime.timedelta(weeks=7)

        inside_dt = datetime.datetime.combine(
            cls.oldest_monday, datetime.time(0, 30), tzinfo=datetime.UTC
        )
        outside_dt = datetime.datetime.combine(
            cls.oldest_monday - datetime.timedelta(days=1),
            datetime.time(23, 30),
            tzinfo=datetime.UTC,
        )

        cls.inside = CharacterXPTransactionFactory(character=cls.sheet, amount=10)
        CharacterXPTransaction.objects.filter(pk=cls.inside.pk).update(transaction_date=inside_dt)

        cls.outside = CharacterXPTransactionFactory(character=cls.sheet, amount=20)
        CharacterXPTransaction.objects.filter(pk=cls.outside.pk).update(transaction_date=outside_dt)

    def test_weekly_window_boundary_inclusion_and_exclusion(self) -> None:
        series = progression_series(weeks=8)
        xp_series = next(s for s in series if s.label == "XP earned")
        assert xp_series.points[0].week_start == self.oldest_monday
        assert xp_series.points[0].value == 10.0
        # The outside row must not surface in any bucket -- the sum across
        # the whole series should equal only the inside row's amount.
        assert sum(point.value for point in xp_series.points) == 10.0


class LevelDistributionTests(TestCase):
    def setUp(self) -> None:
        self.klass = CharacterClassFactory()

    def test_only_primary_class_levels_counted(self) -> None:
        CharacterClassLevelFactory(character_class=self.klass, level=5, is_primary=True)
        CharacterClassLevelFactory(character_class=self.klass, level=5, is_primary=True)
        # Non-primary at level 5 must not be counted.
        CharacterClassLevelFactory(character_class=self.klass, level=5, is_primary=False)
        CharacterClassLevelFactory(character_class=self.klass, level=3, is_primary=True)

        rows = level_distribution()
        assert (5, 2) in rows
        assert (3, 1) in rows
        assert sum(count for _level, count in rows) == 3


class EconomySeriesTests(TestCase):
    """Mint/sink/transfer classification for `economy_series`."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.monday = _this_monday()
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        cls.purse_a = get_or_create_purse(sheet_a)
        cls.purse_b = get_or_create_purse(sheet_b)
        # Fund purse_a so a purse-to-purse transfer is solvent.
        cls.purse_a.balance = 500
        cls.purse_a.save()

        cls.mint = transfer(amount=100, reason="mint test", to_purse=cls.purse_a)
        cls.sink = transfer(amount=50, reason="sink test", from_purse=cls.purse_a)
        cls.moved = transfer(
            amount=30, reason="transfer test", from_purse=cls.purse_a, to_purse=cls.purse_b
        )
        for row in (cls.mint, cls.sink, cls.moved):
            type(row).objects.filter(pk=row.pk).update(created_at=timezone.now())

    def test_null_source_counts_as_minted(self) -> None:
        series = economy_series(weeks=8)
        minted = next(s for s in series if s.label == "Minted")
        assert minted.points[-1].value == 100.0

    def test_null_destination_counts_as_sunk(self) -> None:
        series = economy_series(weeks=8)
        sunk = next(s for s in series if s.label == "Sunk")
        assert sunk.points[-1].value == 50.0

    def test_both_sides_populated_counts_as_transferred(self) -> None:
        series = economy_series(weeks=8)
        transferred = next(s for s in series if s.label == "Transferred")
        assert transferred.points[-1].value == 30.0

    def test_one_query_per_series(self) -> None:
        with self.assertNumQueries(3):
            economy_series(weeks=8)


class MoneySupplyTests(TestCase):
    def test_totals_sum_purses_and_treasuries(self) -> None:
        sheet = CharacterSheetFactory()
        purse = get_or_create_purse(sheet)
        purse.balance = 40
        purse.save()

        org = OrganizationFactory()
        treasury = get_or_create_treasury(org)
        treasury.balance = 60
        treasury.save()

        supply = money_supply()
        assert supply["purses"] == 40
        assert supply["treasuries"] == 60
        assert supply["total"] == 100

    def test_empty_tables_yield_zero_not_none(self) -> None:
        CharacterPurse.objects.all().delete()
        OrganizationTreasury.objects.all().delete()
        assert money_supply() == {"purses": 0, "treasuries": 0, "total": 0}


class StorySeriesAndSnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.monday = _this_monday()

    def test_story_series_labels(self) -> None:
        series = story_series(weeks=8)
        labels = {s.label for s in series}
        assert labels == {"Beats completed", "Scenes started"}

    def test_one_query_per_series(self) -> None:
        with self.assertNumQueries(2):
            story_series(weeks=8)

    def test_snapshot_counts_by_status(self) -> None:
        StoryFactory(status=StoryStatus.ACTIVE)
        StoryFactory(status=StoryStatus.INACTIVE)
        GMTableFactory(status=GMTableStatus.ACTIVE)
        GMTableFactory(status=GMTableStatus.ARCHIVED)
        # SessionRequestFactory's nested episode->chapter->story chain creates
        # its own Story (default ACTIVE) unless pinned INACTIVE here — keep
        # the active_stories count isolated to the explicit row above.
        SessionRequestFactory(
            status=SessionRequestStatus.OPEN, episode__chapter__story__status=StoryStatus.INACTIVE
        )
        SessionRequestFactory(
            status=SessionRequestStatus.SCHEDULED,
            episode__chapter__story__status=StoryStatus.INACTIVE,
        )

        active_gm = GMProfileFactory()
        active_gm.last_active_at = timezone.now()
        active_gm.save()
        stale_gm = GMProfileFactory()
        stale_gm.last_active_at = timezone.now() - datetime.timedelta(days=45)
        stale_gm.save()
        # Never-active GM (null last_active_at) must not count as active.
        GMProfileFactory()

        snapshot = story_snapshot()
        assert snapshot["active_stories"] == 1
        assert snapshot["active_gm_tables"] == 1
        assert snapshot["pending_session_requests"] == 1
        assert snapshot["gms_active_30d"] == 1


class ReportsSnapshotTests(TestCase):
    def test_open_count_excludes_terminal_statuses(self) -> None:
        PlayerFeedbackFactory(status=SubmissionStatus.OPEN)
        PlayerFeedbackFactory(status=SubmissionStatus.OPEN)
        PlayerFeedbackFactory(status=SubmissionStatus.REVIEWED)
        PlayerFeedbackFactory(status=SubmissionStatus.DISMISSED)

        buckets = reports_snapshot()
        feedback_bucket = next(b for b in buckets if b.kind == "Player Feedback")
        assert feedback_bucket.open_count == 2
        assert feedback_bucket.total == 4
        assert feedback_bucket.staff_url == "/staff/feedback"

    def test_all_four_kinds_present(self) -> None:
        buckets = reports_snapshot()
        kinds = {b.kind for b in buckets}
        assert kinds == {"Player Feedback", "Bug Reports", "Player Reports", "System Errors"}

    def test_staff_urls(self) -> None:
        buckets = {b.kind: b.staff_url for b in reports_snapshot()}
        assert buckets["Bug Reports"] == "/staff/bug-reports"
        assert buckets["Player Reports"] == "/staff/player-reports"
        assert buckets["System Errors"] == "/staff/system-errors"

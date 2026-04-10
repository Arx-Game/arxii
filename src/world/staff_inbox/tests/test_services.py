"""Tests for staff inbox aggregator service."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.player_submissions.constants import SubmissionCategory, SubmissionStatus
from world.player_submissions.factories import (
    BugReportFactory,
    PlayerFeedbackFactory,
    PlayerReportFactory,
)
from world.player_submissions.models import PlayerFeedback
from world.staff_inbox.services import get_staff_inbox


class StaffInboxAggregatorTest(TestCase):
    def test_includes_open_feedback(self) -> None:
        fb = PlayerFeedbackFactory()
        items = get_staff_inbox()
        source_types = {i.source_type for i in items}
        self.assertIn(SubmissionCategory.PLAYER_FEEDBACK, source_types)
        self.assertTrue(any(i.source_pk == fb.pk for i in items))

    def test_filters_by_category(self) -> None:
        PlayerFeedbackFactory()
        BugReportFactory()
        items = get_staff_inbox(categories=[SubmissionCategory.BUG_REPORT])
        source_types = {i.source_type for i in items}
        self.assertEqual(source_types, {SubmissionCategory.BUG_REPORT})

    def test_sorted_by_created_at_desc(self) -> None:
        fb1 = PlayerFeedbackFactory()
        fb2 = PlayerFeedbackFactory()
        # Force fb2 to be newer
        PlayerFeedback.objects.filter(pk=fb2.pk).update(
            created_at=timezone.now() + timedelta(hours=1),
        )
        items = get_staff_inbox(categories=[SubmissionCategory.PLAYER_FEEDBACK])
        self.assertEqual(items[0].source_pk, fb2.pk)
        self.assertEqual(items[1].source_pk, fb1.pk)

    def test_excludes_non_open_status(self) -> None:
        fb = PlayerFeedbackFactory(status=SubmissionStatus.REVIEWED)
        items = get_staff_inbox(categories=[SubmissionCategory.PLAYER_FEEDBACK])
        self.assertFalse(any(i.source_pk == fb.pk for i in items))

    def test_player_report_included(self) -> None:
        pr = PlayerReportFactory()
        items = get_staff_inbox(categories=[SubmissionCategory.PLAYER_REPORT])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_pk, pr.pk)

"""Tests for player submission models."""

from django.test import TestCase

from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.factories import (
    BugReportFactory,
    PlayerFeedbackFactory,
    PlayerReportFactory,
)
from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport


class PlayerFeedbackModelTest(TestCase):
    def test_creates_feedback(self) -> None:
        fb = PlayerFeedbackFactory()
        assert PlayerFeedback.objects.filter(pk=fb.pk).exists()
        assert fb.status == SubmissionStatus.OPEN
        assert fb.reporter_persona is not None

    def test_has_default_ordering(self) -> None:
        fb1 = PlayerFeedbackFactory()
        fb2 = PlayerFeedbackFactory()
        results = list(PlayerFeedback.objects.all())
        # Ordered by -created_at so newer first
        assert results[0] == fb2
        assert results[1] == fb1


class BugReportModelTest(TestCase):
    def test_creates_bug_report(self) -> None:
        br = BugReportFactory()
        assert BugReport.objects.filter(pk=br.pk).exists()
        assert br.status == SubmissionStatus.OPEN


class PlayerReportModelTest(TestCase):
    def test_creates_player_report(self) -> None:
        pr = PlayerReportFactory()
        assert PlayerReport.objects.filter(pk=pr.pk).exists()
        assert pr.reporter_persona != pr.reported_persona

    def test_default_flags(self) -> None:
        pr = PlayerReportFactory()
        assert pr.asked_to_stop is False
        assert pr.blocked_or_muted is False

"""Tests for draft application service functions."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import ApplicationStatus, CommentType
from world.character_creation.factories import (
    CharacterDraftFactory,
    DraftApplicationFactory,
)
from world.character_creation.models import DraftApplication, DraftApplicationComment
from world.character_creation.services import (
    resubmit_draft,
    submit_draft_for_review,
    unsubmit_draft,
    withdraw_draft,
)


class SubmitDraftForReviewTests(TestCase):
    """Tests for submit_draft_for_review service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def _make_submittable_draft(self):
        draft = CharacterDraftFactory(account=self.account)
        draft.can_submit = lambda: True
        return draft

    def test_creates_application(self):
        """Creates a DraftApplication with SUBMITTED status and submission notes."""
        draft = self._make_submittable_draft()
        app = submit_draft_for_review(draft, submission_notes="Please review!")

        self.assertIsInstance(app, DraftApplication)
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertEqual(app.submission_notes, "Please review!")
        self.assertEqual(app.draft, draft)

    def test_creates_status_change_comment(self):
        """Creates 1 STATUS_CHANGE comment saying 'Application submitted for review.'"""
        draft = self._make_submittable_draft()
        app = submit_draft_for_review(draft)

        comments = DraftApplicationComment.objects.filter(application=app)
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comment.text, "Application submitted for review.")
        self.assertIsNone(comment.author)

    def test_raises_if_already_has_application(self):
        """Raises ValueError if draft already has an application."""
        draft = self._make_submittable_draft()
        DraftApplicationFactory(draft=draft)

        with self.assertRaises(ValueError, msg="This draft already has an application."):
            submit_draft_for_review(draft)

    def test_raises_if_draft_cannot_submit(self):
        """Raises ValueError if draft.can_submit() returns False."""
        draft = CharacterDraftFactory(account=self.account)
        draft.can_submit = lambda: False

        with self.assertRaises(ValueError, msg="Draft is not complete enough to submit."):
            submit_draft_for_review(draft)


class UnsubmitDraftTests(TestCase):
    """Tests for unsubmit_draft service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def test_unsubmit_returns_to_editable(self):
        """Sets status to REVISIONS_REQUESTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )
        unsubmit_draft(app)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.REVISIONS_REQUESTED)

    def test_creates_status_change_comment(self):
        """Creates STATUS_CHANGE 'Player resumed editing.'"""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )
        unsubmit_draft(app)

        comments = DraftApplicationComment.objects.filter(application=app)
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comment.text, "Player resumed editing.")
        self.assertIsNone(comment.author)

    def test_raises_if_not_submitted(self):
        """Raises ValueError if status is not SUBMITTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.IN_REVIEW
        )

        with self.assertRaises(ValueError):
            unsubmit_draft(app)


class ResubmitDraftTests(TestCase):
    """Tests for resubmit_draft service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def test_resubmit_sets_submitted(self):
        """Sets status to SUBMITTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.REVISIONS_REQUESTED
        )
        resubmit_draft(app)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)

    def test_creates_message_and_status_comments(self):
        """Creates MESSAGE (if comment provided) + STATUS_CHANGE."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.REVISIONS_REQUESTED
        )
        resubmit_draft(app, comment="Fixed the backstory.")

        comments = list(
            DraftApplicationComment.objects.filter(application=app).order_by("created_at")
        )
        self.assertEqual(len(comments), 2)

        # First comment should be the MESSAGE
        self.assertEqual(comments[0].comment_type, CommentType.MESSAGE)
        self.assertEqual(comments[0].text, "Fixed the backstory.")
        self.assertEqual(comments[0].author, self.account)

        # Second comment should be the STATUS_CHANGE
        self.assertEqual(comments[1].comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comments[1].text, "Application resubmitted for review.")
        self.assertIsNone(comments[1].author)

    def test_resubmit_without_comment(self):
        """Only creates STATUS_CHANGE, no MESSAGE."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.REVISIONS_REQUESTED
        )
        resubmit_draft(app)

        comments = DraftApplicationComment.objects.filter(application=app)
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comment.text, "Application resubmitted for review.")

    def test_raises_if_not_revisions_requested(self):
        """Raises ValueError if status is not REVISIONS_REQUESTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )

        with self.assertRaises(ValueError):
            resubmit_draft(app)


class WithdrawDraftTests(TestCase):
    """Tests for withdraw_draft service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def test_withdraw_sets_status_and_expiry(self):
        """Sets WITHDRAWN and non-null expires_at."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )
        withdraw_draft(app)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.WITHDRAWN)
        self.assertIsNotNone(app.expires_at)

    def test_expires_at_is_two_weeks_out(self):
        """expires_at is ~14 days from now."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )
        before = timezone.now()
        withdraw_draft(app)
        after = timezone.now()

        app.refresh_from_db()
        expected_min = before + timedelta(days=14)
        expected_max = after + timedelta(days=14)
        self.assertGreaterEqual(app.expires_at, expected_min)
        self.assertLessEqual(app.expires_at, expected_max)

    def test_raises_if_terminal(self):
        """Raises ValueError if already APPROVED/DENIED/WITHDRAWN."""
        for status in (
            ApplicationStatus.APPROVED,
            ApplicationStatus.DENIED,
            ApplicationStatus.WITHDRAWN,
        ):
            app = DraftApplicationFactory(draft__account=self.account, status=status)
            with self.assertRaises(ValueError):
                withdraw_draft(app)

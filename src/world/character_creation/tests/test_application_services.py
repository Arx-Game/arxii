"""Tests for draft application service functions."""

from datetime import timedelta
from unittest.mock import patch

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
    CharacterCreationError,
    add_application_comment,
    approve_application,
    claim_application,
    deny_application,
    request_revisions,
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
        """Raises CharacterCreationError if draft already has an application."""
        draft = self._make_submittable_draft()
        DraftApplicationFactory(draft=draft)

        with self.assertRaises(CharacterCreationError):
            submit_draft_for_review(draft)

    def test_raises_if_draft_cannot_submit(self):
        """Raises CharacterCreationError if draft.can_submit() returns False."""
        draft = CharacterDraftFactory(account=self.account)
        draft.can_submit = lambda: False

        with self.assertRaises(CharacterCreationError):
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
        """Raises CharacterCreationError if status is not SUBMITTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.IN_REVIEW
        )

        with self.assertRaises(CharacterCreationError):
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
        """Raises CharacterCreationError if status is not REVISIONS_REQUESTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )

        with self.assertRaises(CharacterCreationError):
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
        """Raises CharacterCreationError if already APPROVED/DENIED/WITHDRAWN."""
        for status in (
            ApplicationStatus.APPROVED,
            ApplicationStatus.DENIED,
            ApplicationStatus.WITHDRAWN,
        ):
            app = DraftApplicationFactory(draft__account=self.account, status=status)
            with self.assertRaises(CharacterCreationError):
                withdraw_draft(app)


# ── Staff Review Service Tests ──────────────────────────────────────────────


class ClaimApplicationTests(TestCase):
    """Tests for claim_application service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    def test_claim_sets_in_review(self):
        """Sets status to IN_REVIEW and assigns reviewer."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        claim_application(app, reviewer=self.staff)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.IN_REVIEW)
        self.assertEqual(app.reviewer, self.staff)

    def test_claim_sets_reviewed_at(self):
        """Sets reviewed_at timestamp."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        before = timezone.now()
        claim_application(app, reviewer=self.staff)
        after = timezone.now()
        app.refresh_from_db()
        self.assertIsNotNone(app.reviewed_at)
        self.assertGreaterEqual(app.reviewed_at, before)
        self.assertLessEqual(app.reviewed_at, after)

    def test_claim_creates_status_change_comment(self):
        """Creates STATUS_CHANGE comment: 'Claimed for review by {username}.'"""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        claim_application(app, reviewer=self.staff)

        comments = DraftApplicationComment.objects.filter(application=app)
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comment.text, f"Claimed for review by {self.staff.username}.")
        self.assertIsNone(comment.author)

    def test_raises_if_not_submitted(self):
        """Raises CharacterCreationError if status is not SUBMITTED."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.REVISIONS_REQUESTED)
        with self.assertRaises(CharacterCreationError):
            claim_application(app, reviewer=self.staff)


class ApproveApplicationTests(TestCase):
    """Tests for approve_application service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    @patch("world.character_creation.services.finalize_character")
    def test_approve_finalizes_character(self, mock_finalize):
        """Calls finalize_character(draft, add_to_roster=False)."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        approve_application(app, reviewer=self.staff, comment="Looks great!")
        mock_finalize.assert_called_once_with(draft, add_to_roster=False)

    @patch("world.character_creation.services.finalize_character")
    def test_approve_sets_status(self, mock_finalize):
        """Sets status to APPROVED."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        approve_application(app, reviewer=self.staff)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.APPROVED)

    @patch("world.character_creation.services.finalize_character")
    def test_approve_sets_reviewer_and_reviewed_at(self, mock_finalize):
        """Sets reviewer and reviewed_at."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        before = timezone.now()
        approve_application(app, reviewer=self.staff)
        after = timezone.now()
        app.refresh_from_db()
        self.assertEqual(app.reviewer, self.staff)
        self.assertIsNotNone(app.reviewed_at)
        self.assertGreaterEqual(app.reviewed_at, before)
        self.assertLessEqual(app.reviewed_at, after)

    @patch("world.character_creation.services.finalize_character")
    def test_approve_creates_message_comment_if_provided(self, mock_finalize):
        """Creates MESSAGE comment when comment text is provided."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        approve_application(app, reviewer=self.staff, comment="Great character!")

        comments = list(
            DraftApplicationComment.objects.filter(application=app).order_by("created_at")
        )
        self.assertEqual(len(comments), 2)

        # First comment is the MESSAGE
        self.assertEqual(comments[0].comment_type, CommentType.MESSAGE)
        self.assertEqual(comments[0].text, "Great character!")
        self.assertEqual(comments[0].author, self.staff)

    @patch("world.character_creation.services.finalize_character")
    def test_approve_creates_status_change_comment(self, mock_finalize):
        """Creates STATUS_CHANGE comment: 'Application approved by {username}.'"""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        approve_application(app, reviewer=self.staff)

        comments = DraftApplicationComment.objects.filter(
            application=app, comment_type=CommentType.STATUS_CHANGE
        )
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.text, f"Application approved by {self.staff.username}.")
        self.assertIsNone(comment.author)

    def test_raises_if_not_in_review(self):
        """Raises CharacterCreationError if status is not IN_REVIEW."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        with self.assertRaises(CharacterCreationError):
            approve_application(app, reviewer=self.staff)


class RequestRevisionsTests(TestCase):
    """Tests for request_revisions service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    def test_sets_revisions_requested(self):
        """Sets status to REVISIONS_REQUESTED."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        request_revisions(app, reviewer=self.staff, comment="Please fix backstory.")
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.REVISIONS_REQUESTED)

    def test_sets_reviewed_at(self):
        """Sets reviewed_at timestamp."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        before = timezone.now()
        request_revisions(app, reviewer=self.staff, comment="Please fix backstory.")
        after = timezone.now()
        app.refresh_from_db()
        self.assertIsNotNone(app.reviewed_at)
        self.assertGreaterEqual(app.reviewed_at, before)
        self.assertLessEqual(app.reviewed_at, after)

    def test_creates_message_and_status_comments(self):
        """Creates MESSAGE with feedback + STATUS_CHANGE comment."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        request_revisions(app, reviewer=self.staff, comment="Please fix backstory.")

        comments = list(
            DraftApplicationComment.objects.filter(application=app).order_by("created_at")
        )
        self.assertEqual(len(comments), 2)

        # First comment is the MESSAGE
        self.assertEqual(comments[0].comment_type, CommentType.MESSAGE)
        self.assertEqual(comments[0].text, "Please fix backstory.")
        self.assertEqual(comments[0].author, self.staff)

        # Second comment is the STATUS_CHANGE
        self.assertEqual(comments[1].comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comments[1].text, f"Revisions requested by {self.staff.username}.")
        self.assertIsNone(comments[1].author)

    def test_raises_if_not_in_review(self):
        """Raises CharacterCreationError if status is not IN_REVIEW."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        with self.assertRaises(CharacterCreationError):
            request_revisions(app, reviewer=self.staff, comment="Fix it.")

    def test_raises_if_comment_empty(self):
        """Raises CharacterCreationError if comment is empty."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        with self.assertRaises(CharacterCreationError):
            request_revisions(app, reviewer=self.staff, comment="")


class DenyApplicationTests(TestCase):
    """Tests for deny_application service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    def test_deny_sets_status(self):
        """Sets status to DENIED."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.DENIED)

    def test_deny_sets_reviewer_and_reviewed_at(self):
        """Sets reviewer and reviewed_at."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        before = timezone.now()
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")
        after = timezone.now()
        app.refresh_from_db()
        self.assertEqual(app.reviewer, self.staff)
        self.assertIsNotNone(app.reviewed_at)
        self.assertGreaterEqual(app.reviewed_at, before)
        self.assertLessEqual(app.reviewed_at, after)

    def test_deny_sets_expires_at(self):
        """Sets expires_at to ~14 days from now."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        before = timezone.now()
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")
        after = timezone.now()
        app.refresh_from_db()
        self.assertIsNotNone(app.expires_at)
        self.assertGreaterEqual(app.expires_at, before + timedelta(days=14))
        self.assertLessEqual(app.expires_at, after + timedelta(days=14))

    def test_deny_creates_message_and_status_comments(self):
        """Creates MESSAGE with denial reason + STATUS_CHANGE comment."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")

        comments = list(
            DraftApplicationComment.objects.filter(application=app).order_by("created_at")
        )
        self.assertEqual(len(comments), 2)

        # First comment is the MESSAGE
        self.assertEqual(comments[0].comment_type, CommentType.MESSAGE)
        self.assertEqual(comments[0].text, "Concept doesn't fit.")
        self.assertEqual(comments[0].author, self.staff)

        # Second comment is the STATUS_CHANGE
        self.assertEqual(comments[1].comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comments[1].text, f"Application denied by {self.staff.username}.")
        self.assertIsNone(comments[1].author)

    def test_raises_if_not_in_review(self):
        """Raises CharacterCreationError if status is not IN_REVIEW."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        with self.assertRaises(CharacterCreationError):
            deny_application(app, reviewer=self.staff, comment="No.")

    def test_raises_if_comment_empty(self):
        """Raises CharacterCreationError if comment is empty."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        with self.assertRaises(CharacterCreationError):
            deny_application(app, reviewer=self.staff, comment="")


class AddApplicationCommentTests(TestCase):
    """Tests for add_application_comment service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    def test_creates_message_comment(self):
        """Creates a MESSAGE comment with given text and author."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.IN_REVIEW)
        comment = add_application_comment(app, author=self.staff, text="Looking good so far.")

        self.assertIsInstance(comment, DraftApplicationComment)
        self.assertEqual(comment.application, app)
        self.assertEqual(comment.author, self.staff)
        self.assertEqual(comment.text, "Looking good so far.")
        self.assertEqual(comment.comment_type, CommentType.MESSAGE)

    def test_raises_if_text_empty(self):
        """Raises CharacterCreationError if text is empty."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.IN_REVIEW)
        with self.assertRaises(CharacterCreationError):
            add_application_comment(app, author=self.staff, text="")

    def test_returns_created_comment(self):
        """Returns the created DraftApplicationComment instance."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.IN_REVIEW)
        result = add_application_comment(app, author=self.account, text="Player question.")

        self.assertEqual(result.pk, DraftApplicationComment.objects.get(application=app).pk)

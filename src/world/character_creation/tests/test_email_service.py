"""Tests for CG application review email notifications (#2162)."""

from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import ApplicationStatus
from world.character_creation.email_service import CGEmailService
from world.character_creation.factories import CharacterDraftFactory, DraftApplicationFactory
from world.character_creation.services import (
    approve_application,
    deny_application,
    request_revisions,
    submit_draft_for_review,
)


class CGEmailTests(TestCase):
    """Tests for CGEmailService, exercised via the CG review service functions."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(email="applicant@example.com")
        cls.staff = AccountFactory(is_staff=True)

    def _make_application(self, status=ApplicationStatus.IN_REVIEW):
        draft = CharacterDraftFactory(account=self.account)
        return DraftApplicationFactory(
            draft=draft,
            player_account=self.account,
            status=status,
            reviewer=self.staff,
        )

    @patch("world.character_creation.services.RosterTenure")
    @patch("world.character_creation.services.finalize_character")
    def test_approve_sends_email_to_applicant(self, mock_finalize, mock_tenure_cls):  # noqa: ARG002
        app = self._make_application()
        approve_application(app, reviewer=self.staff, comment="ok")

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.account.email, mail.outbox[0].to)
        self.assertIn("approved", mail.outbox[0].subject.lower())

    def test_deny_sends_email(self):
        app = self._make_application()
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.account.email, mail.outbox[0].to)
        subject = mail.outbox[0].subject.lower()
        self.assertTrue("denied" in subject or "not approved" in subject)

    def test_revisions_sends_email(self):
        app = self._make_application()
        request_revisions(app, reviewer=self.staff, comment="Please fix backstory.")

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.account.email, mail.outbox[0].to)
        self.assertIn("revision", mail.outbox[0].subject.lower())

    @override_settings(STAFF_NOTIFICATION_EMAILS=["staff@test.com"])
    def test_submission_sends_confirmation_and_staff_notification(self):
        draft = CharacterDraftFactory(account=self.account)
        draft.can_submit = lambda: True

        submit_draft_for_review(draft)

        self.assertEqual(len(mail.outbox), 2)
        recipients = [addr for message in mail.outbox for addr in message.to]
        self.assertIn(self.account.email, recipients)
        self.assertIn("staff@test.com", recipients)

    @patch("world.character_creation.services.RosterTenure")
    @patch("world.character_creation.services.finalize_character")
    def test_email_failure_does_not_break_approval(
        self,
        mock_finalize,  # noqa: ARG002
        mock_tenure_cls,  # noqa: ARG002
    ):
        app = self._make_application()

        with patch.object(
            CGEmailService, "send_application_approved", side_effect=Exception("boom")
        ):
            approve_application(app, reviewer=self.staff)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.APPROVED)

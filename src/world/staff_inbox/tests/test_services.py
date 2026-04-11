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


class AccountHistoryTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory, CharacterFactory
        from world.character_sheets.factories import CharacterIdentityFactory
        from world.roster.factories import RosterTenureFactory

        cls.account = AccountFactory()
        cls.character = CharacterFactory(db_key="Target")
        cls.identity = CharacterIdentityFactory(character=cls.character)
        cls.persona = cls.identity.active_persona
        cls.tenure = RosterTenureFactory(
            roster_entry__character=cls.character,
            player_data__account=cls.account,
        )

    def test_history_includes_own_feedback(self) -> None:
        from world.staff_inbox.services import get_account_submission_history

        fb = PlayerFeedbackFactory(reporter_persona=self.persona)
        history = get_account_submission_history(account_id=self.account.pk)
        self.assertEqual(len(history["feedback"]["items"]), 1)
        self.assertEqual(history["feedback"]["items"][0].source_pk, fb.pk)
        self.assertEqual(history["feedback"]["total"], 1)
        self.assertFalse(history["feedback"]["truncated"])

    def test_history_includes_reports_against(self) -> None:
        from world.staff_inbox.services import get_account_submission_history

        pr = PlayerReportFactory(reported_persona=self.persona)
        history = get_account_submission_history(account_id=self.account.pk)
        self.assertEqual(len(history["reports_against"]["items"]), 1)
        self.assertEqual(history["reports_against"]["items"][0].source_pk, pr.pk)
        self.assertEqual(history["reports_against"]["total"], 1)

    def test_history_includes_reports_submitted(self) -> None:
        from world.staff_inbox.services import get_account_submission_history

        pr = PlayerReportFactory(reporter_persona=self.persona)
        history = get_account_submission_history(account_id=self.account.pk)
        self.assertEqual(len(history["reports_submitted"]["items"]), 1)
        self.assertEqual(history["reports_submitted"]["items"][0].source_pk, pr.pk)

    def test_history_includes_bug_reports(self) -> None:
        from world.staff_inbox.services import get_account_submission_history

        br = BugReportFactory(reporter_persona=self.persona)
        history = get_account_submission_history(account_id=self.account.pk)
        self.assertEqual(len(history["bug_reports"]["items"]), 1)
        self.assertEqual(history["bug_reports"]["items"][0].source_pk, br.pk)

    def test_history_empty_for_unrelated_account(self) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.staff_inbox.services import get_account_submission_history

        PlayerFeedbackFactory(reporter_persona=self.persona)
        other_account = AccountFactory()
        history = get_account_submission_history(account_id=other_account.pk)
        self.assertEqual(len(history["feedback"]["items"]), 0)
        self.assertEqual(history["feedback"]["total"], 0)
        self.assertFalse(history["feedback"]["truncated"])

    def test_format_summary_no_account_falls_back_to_player_only(self) -> None:
        from world.staff_inbox.services import format_identity_summary

        result = format_identity_summary(("Alice", 1, ""), include_account=True)
        self.assertEqual(result, "Alice (Player 1)")

    def test_format_summary_no_player_falls_back_to_name(self) -> None:
        """None player_num means no active tenure — just show the name."""
        from world.staff_inbox.services import format_identity_summary

        result = format_identity_summary(("Alice", None, ""), include_account=True)
        self.assertEqual(result, "Alice")

    def test_format_summary_with_player_zero(self) -> None:
        """player_number=0 is a valid player (first player of char)."""
        from world.staff_inbox.services import format_identity_summary

        result = format_identity_summary(("Alice", 0, "bob"), include_account=True)
        self.assertEqual(result, "Alice (Player 0, Account bob)")

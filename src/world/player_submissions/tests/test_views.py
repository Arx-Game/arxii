"""Tests for player submission ViewSets."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.player_submissions.factories import (
    PlayerFeedbackFactory,
    PlayerReportFactory,
)
from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import PersonaFactory


class PlayerFeedbackCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="testplayer")
        cls.character = CharacterFactory(db_key="TestChar")
        cls.identity = CharacterIdentityFactory(character=cls.character)
        cls.persona = cls.identity.active_persona
        cls.tenure = RosterTenureFactory(
            roster_entry__character=cls.character,
            player_data__account=cls.account,
        )

    def test_authenticated_player_can_submit(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/feedback/",
            {"description": "Love the new combat system!"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        fb = PlayerFeedback.objects.get()
        self.assertEqual(fb.reporter_persona, self.persona)

    def test_unauthenticated_cannot_submit(self) -> None:
        client = APIClient()
        response = client.post(
            "/api/player-submissions/feedback/",
            {"description": "anon rant"},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))


class PlayerFeedbackListTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff_account = AccountFactory(username="staffuser", is_staff=True)
        cls.regular_account = AccountFactory(username="regular")
        PlayerFeedbackFactory.create_batch(3)

    def test_staff_can_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get("/api/player-submissions/feedback/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

    def test_non_staff_cannot_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular_account)
        response = client.get("/api/player-submissions/feedback/")
        self.assertEqual(response.status_code, 403)


class BugReportCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="buguser")
        cls.character = CharacterFactory(db_key="BugChar")
        cls.identity = CharacterIdentityFactory(character=cls.character)
        cls.persona = cls.identity.active_persona
        cls.tenure = RosterTenureFactory(
            roster_entry__character=cls.character,
            player_data__account=cls.account,
        )

    def test_can_submit_bug_report(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/bug-reports/",
            {"description": "Scene timer desyncs"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(BugReport.objects.count(), 1)


class PlayerReportCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="reporter")
        cls.character = CharacterFactory(db_key="ReporterChar")
        cls.identity = CharacterIdentityFactory(character=cls.character)
        cls.reporter_persona = cls.identity.active_persona
        cls.tenure = RosterTenureFactory(
            roster_entry__character=cls.character,
            player_data__account=cls.account,
        )
        cls.target_persona = PersonaFactory()

    def test_can_submit_report(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/player-reports/",
            {
                "reported_persona": self.target_persona.pk,
                "behavior_description": "harassing behavior",
                "asked_to_stop": True,
                "blocked_or_muted": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        report = PlayerReport.objects.get()
        self.assertEqual(report.reporter_persona, self.reporter_persona)
        self.assertEqual(report.reported_persona, self.target_persona)

    def test_staff_detail_shows_account(self) -> None:
        staff = AccountFactory(username="staffuser", is_staff=True)
        # Build a report whose reporter has the full character+tenure chain
        # so the identity summary can surface the account name for staff.
        reporter_account = AccountFactory(username="reportowner")
        reporter_char = CharacterFactory(db_key="ReportedReporter")
        reporter_identity = CharacterIdentityFactory(character=reporter_char)
        RosterTenureFactory(
            roster_entry__character=reporter_char,
            player_data__account=reporter_account,
        )
        report = PlayerReportFactory(reporter_persona=reporter_identity.active_persona)
        client = APIClient()
        client.force_authenticate(user=staff)
        response = client.get(
            f"/api/player-submissions/player-reports/{report.pk}/",
        )
        self.assertEqual(response.status_code, 200)
        # Account portion visible to staff
        self.assertIn("Account", response.data["reporter_summary"])

"""Tests for player submission ViewSets."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterIdentityFactory
from world.player_submissions.factories import (
    BugReportFactory,
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

    def test_location_auto_populated_from_character(self) -> None:
        """The location field is set from character.location on create."""
        # Refresh to prevent cross-test pollution from the identity-map
        # cache under setUpTestData.
        self.character.refresh_from_db()
        room = RoomProfileFactory().objectdb
        self.character.location = room

        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/feedback/",
            {"description": "in a room"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        fb = PlayerFeedback.objects.get()
        self.assertEqual(fb.location_id, room.pk)

    def test_client_location_field_is_ignored(self) -> None:
        """Client-supplied location in POST body is ignored."""
        self.character.refresh_from_db()
        character_room = RoomProfileFactory().objectdb
        other_room = RoomProfileFactory().objectdb
        self.character.location = character_room

        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/feedback/",
            {"description": "test", "location": other_room.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        fb = PlayerFeedback.objects.get()
        # Should be character_room, not the client-supplied other_room
        self.assertEqual(fb.location_id, character_room.pk)

    def test_location_picks_up_out_of_band_updates(self) -> None:
        """If db_location was updated out-of-band (raw SQL or another
        process), perform_create must still pick up the current location,
        not a stale cache."""
        from evennia.objects.models import ObjectDB

        self.character.refresh_from_db()
        initial_room = RoomProfileFactory().objectdb
        self.character.db_location = initial_room
        self.character.save()

        # Access the identity-mapped instance so it's in cache
        _ = self.character.db_location

        # Simulate out-of-band update (bypassing the identity map)
        new_room = RoomProfileFactory().objectdb
        ObjectDB.objects.filter(pk=self.character.pk).update(db_location=new_room)

        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/feedback/",
            {"description": "test"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        fb = PlayerFeedback.objects.get()
        self.assertEqual(fb.location_id, new_room.pk)


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


class PlayerReportPermissionTest(TestCase):
    """Safety-critical: verify non-staff cannot access player reports."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="permstaff", is_staff=True)
        cls.regular = AccountFactory(username="permregular")
        cls.report = PlayerReportFactory()

    def test_unauthenticated_cannot_list(self) -> None:
        client = APIClient()
        response = client.get("/api/player-submissions/player-reports/")
        self.assertIn(response.status_code, (401, 403))

    def test_regular_user_cannot_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular)
        response = client.get("/api/player-submissions/player-reports/")
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_retrieve(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular)
        response = client.get(
            f"/api/player-submissions/player-reports/{self.report.pk}/",
        )
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_update(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular)
        response = client.patch(
            f"/api/player-submissions/player-reports/{self.report.pk}/",
            {"status": "reviewed"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_can_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get("/api/player-submissions/player-reports/")
        self.assertEqual(response.status_code, 200)


class BugReportPermissionTest(TestCase):
    """Verify non-staff cannot list/retrieve bug reports."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="bugstaff", is_staff=True)
        cls.regular = AccountFactory(username="bugregular")
        cls.bug = BugReportFactory()

    def test_unauthenticated_cannot_list(self) -> None:
        client = APIClient()
        response = client.get("/api/player-submissions/bug-reports/")
        self.assertIn(response.status_code, (401, 403))

    def test_regular_user_cannot_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular)
        response = client.get("/api/player-submissions/bug-reports/")
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_retrieve(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.regular)
        response = client.get(
            f"/api/player-submissions/bug-reports/{self.bug.pk}/",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_can_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get("/api/player-submissions/bug-reports/")
        self.assertEqual(response.status_code, 200)


class PlayerFeedbackListQueryCountTest(TestCase):
    """Regression guard: list query count must not grow with row count."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="querycount_staff", is_staff=True)

    def _count_queries_for_list(self, row_count: int) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        PlayerFeedback.objects.all().delete()
        for _ in range(row_count):
            PlayerFeedbackFactory()
        client = APIClient()
        client.force_authenticate(user=self.staff)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get("/api/player-submissions/feedback/")
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_list_queries_do_not_grow_with_row_count(self) -> None:
        small = self._count_queries_for_list(2)
        large = self._count_queries_for_list(10)
        # Allow a small constant difference (e.g., pagination count query)
        # but not a per-row growth
        self.assertLess(
            large - small,
            3,
            f"Query count grew from {small} to {large} — N+1 regression",
        )


class PlayerReportListQueryCountTest(TestCase):
    """Regression guard: player report list has two personas per row but
    still constant query count."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="pr_querycount_staff", is_staff=True)

    def _count_queries_for_list(self, row_count: int) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        PlayerReport.objects.all().delete()
        for _ in range(row_count):
            PlayerReportFactory()
        client = APIClient()
        client.force_authenticate(user=self.staff)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get("/api/player-submissions/player-reports/")
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_list_queries_do_not_grow(self) -> None:
        small = self._count_queries_for_list(2)
        large = self._count_queries_for_list(10)
        self.assertLess(
            large - small,
            3,
            f"Query count grew from {small} to {large} — N+1 regression",
        )


class BaseViewSetEnforcementTest(TestCase):
    """Verify __init_subclass__ enforces required method overrides."""

    def test_missing_detail_serializer_raises(self) -> None:
        from world.player_submissions.views import _BaseSubmissionViewSet

        with self.assertRaises(NotImplementedError):

            class BrokenFeedbackViewSet(_BaseSubmissionViewSet):
                queryset = PlayerFeedback.objects.all()

                # Deliberately missing _get_detail_serializer_class override
                def _collect_persona_ids(self, rows):  # type: ignore[override]
                    return []

    def test_missing_collect_persona_ids_raises(self) -> None:
        from world.player_submissions.serializers import (
            PlayerFeedbackDetailSerializer,
        )
        from world.player_submissions.views import _BaseSubmissionViewSet

        with self.assertRaises(NotImplementedError):

            class BrokenBugViewSet(_BaseSubmissionViewSet):
                queryset = BugReport.objects.all()

                def _get_detail_serializer_class(self):  # type: ignore[override]
                    return PlayerFeedbackDetailSerializer

                # Deliberately missing _collect_persona_ids override

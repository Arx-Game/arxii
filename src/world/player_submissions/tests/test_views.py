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


def _create_played_persona(account, key: str = "TestChar"):
    """Build a valid account -> tenure -> character -> persona chain.

    Returns the (character, persona) pair so tests can post valid
    submissions and assert on the resulting rows.
    """
    character = CharacterFactory(db_key=key)
    identity = CharacterIdentityFactory(character=character)
    persona = identity.active_persona
    RosterTenureFactory(
        roster_entry__character_sheet__character=character,
        player_data__account=account,
    )
    return character, persona


class PlayerFeedbackCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="testplayer")
        cls.character, cls.persona = _create_played_persona(cls.account, "TestChar")

    def test_authenticated_player_can_submit(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/feedback/",
            {
                "reporter_persona": self.persona.pk,
                "description": "Love the new combat system!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        fb = PlayerFeedback.objects.get()
        self.assertEqual(fb.reporter_persona, self.persona)
        self.assertEqual(fb.reporter_account, self.account)

    def test_unauthenticated_cannot_submit(self) -> None:
        client = APIClient()
        response = client.post(
            "/api/player-submissions/feedback/",
            {
                "reporter_persona": self.persona.pk,
                "description": "anon rant",
            },
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_cannot_submit_as_persona_not_owned(self) -> None:
        """User cannot submit using a persona they don't currently play."""
        other_account = AccountFactory(username="otherplayer")
        _other_char, other_persona = _create_played_persona(
            other_account,
            key="OtherChar",
        )
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/feedback/",
            {
                "reporter_persona": other_persona.pk,
                "description": "spoofed",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlayerFeedback.objects.count(), 0)

    def test_cannot_submit_as_persona_with_no_tenure(self) -> None:
        """Persona whose character has no active tenure rejects with 400."""
        orphan_persona = PersonaFactory()
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/feedback/",
            {
                "reporter_persona": orphan_persona.pk,
                "description": "no tenure",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

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
            {
                "reporter_persona": self.persona.pk,
                "description": "in a room",
            },
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
            {
                "reporter_persona": self.persona.pk,
                "description": "test",
                "location": other_room.pk,
            },
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
            {
                "reporter_persona": self.persona.pk,
                "description": "test",
            },
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
        cls.character, cls.persona = _create_played_persona(cls.account, "BugChar")

    def test_can_submit_bug_report(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/bug-reports/",
            {
                "reporter_persona": self.persona.pk,
                "description": "Scene timer desyncs",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(BugReport.objects.count(), 1)
        bug = BugReport.objects.get()
        self.assertEqual(bug.reporter_account, self.account)


class PlayerReportCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="reporter")
        cls.character, cls.reporter_persona = _create_played_persona(
            cls.account,
            "ReporterChar",
        )
        cls.target_account = AccountFactory(username="target")
        cls.target_character, cls.target_persona = _create_played_persona(
            cls.target_account,
            "TargetChar",
        )

    def test_can_submit_report(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/player-reports/",
            {
                "reporter_persona": self.reporter_persona.pk,
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
        self.assertEqual(report.reporter_account, self.account)
        self.assertEqual(report.reported_account, self.target_account)

    def test_cannot_report_persona_with_no_tenure(self) -> None:
        """A reported persona with no current player rejects the submission."""
        orphan_persona = PersonaFactory()
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/player-reports/",
            {
                "reporter_persona": self.reporter_persona.pk,
                "reported_persona": orphan_persona.pk,
                "behavior_description": "no tenure target",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_report_self(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            "/api/player-submissions/player-reports/",
            {
                "reporter_persona": self.reporter_persona.pk,
                "reported_persona": self.reporter_persona.pk,
                "behavior_description": "self",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_staff_detail_shows_account_username(self) -> None:
        staff = AccountFactory(username="staffuser", is_staff=True)
        report = PlayerReportFactory()
        client = APIClient()
        client.force_authenticate(user=staff)
        response = client.get(
            f"/api/player-submissions/player-reports/{report.pk}/",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["reporter_account_username"],
            report.reporter_account.username,
        )
        self.assertEqual(
            response.data["reported_account_username"],
            report.reported_account.username,
        )


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
    """Regression guard: list query count must not grow with row count.

    Pins the select_related approach against any future N+1 regression.
    """

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

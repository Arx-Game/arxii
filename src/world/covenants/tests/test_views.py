"""Tests for covenants API views."""

from django.test import TestCase, tag
from rest_framework import status
from rest_framework.test import APIClient

from world.covenants.factories import CovenantRoleFactory, GearArchetypeCompatibilityFactory
from world.items.constants import GearArchetype


class CovenantsViewTestCase(TestCase):
    """Base test case with authenticated API client."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        cls.user = AccountDB.objects.create_user(
            username="covtestuser",
            email="cov@test.com",
            password="testpass123",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class GearArchetypeCompatibilityViewTests(CovenantsViewTestCase):
    """Tests for GET /api/covenants/gear-compatibilities/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.role = CovenantRoleFactory(name="Sword")
        cls.compat = GearArchetypeCompatibilityFactory(
            covenant_role=cls.role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )

    def test_list_returns_compatibilities(self) -> None:
        """GET list returns seeded compatibility row."""
        response = self.client.get("/api/covenants/gear-compatibilities/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data]
        self.assertIn(self.compat.pk, ids)

    def test_filter_by_covenant_role(self) -> None:
        """Filter by ?covenant_role= narrows to rows for that role only."""
        other_role = CovenantRoleFactory(name="Shield")
        GearArchetypeCompatibilityFactory(
            covenant_role=other_role,
            gear_archetype=GearArchetype.LIGHT_ARMOR,
        )
        response = self.client.get(
            "/api/covenants/gear-compatibilities/", {"covenant_role": self.role.pk}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)
        for row in response.data:
            self.assertEqual(row["covenant_role"], self.role.pk)

    def test_filter_by_gear_archetype(self) -> None:
        """Filter by ?gear_archetype= narrows to rows with that archetype."""
        response = self.client.get(
            "/api/covenants/gear-compatibilities/",
            {"gear_archetype": GearArchetype.HEAVY_ARMOR},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)
        for row in response.data:
            self.assertEqual(row["gear_archetype"], GearArchetype.HEAVY_ARMOR)

    def test_detail_endpoint(self) -> None:
        """GET single row by pk returns the correct record."""
        response = self.client.get(f"/api/covenants/gear-compatibilities/{self.compat.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.compat.pk)
        self.assertEqual(response.data["covenant_role"], self.role.pk)
        self.assertEqual(response.data["gear_archetype"], GearArchetype.HEAVY_ARMOR)
        self.assertIn("gear_archetype_display", response.data)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests receive 403."""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/covenants/gear-compatibilities/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_method_not_allowed(self) -> None:
        """Read-only ViewSet: POST returns 405 Method Not Allowed."""
        response = self.client.post(
            "/api/covenants/gear-compatibilities/",
            {"covenant_role": self.role.pk, "gear_archetype": GearArchetype.HEAVY_ARMOR},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class CharacterCovenantRoleViewTests(CovenantsViewTestCase):
    """Tests for GET /api/covenants/character-roles/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        super().setUpTestData()

        # Character sheet + active tenure for the default user.
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )
        cls.role = CovenantRoleFactory(name="RoleViewTest Sword")
        cls.assignment = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant_role=cls.role,
        )

        # Another user + sheet (for isolation tests).
        cls.other_account = AccountFactory(username="cov_role_other")
        cls.other_sheet = CharacterSheetFactory()
        cls.other_roster_entry = RosterEntryFactory(character_sheet=cls.other_sheet)
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_tenure = RosterTenureFactory(
            roster_entry=cls.other_roster_entry,
            player_data=cls.other_player_data,
            end_date=None,
        )
        cls.other_role = CovenantRoleFactory(name="RoleViewTest Shield")
        cls.other_assignment = CharacterCovenantRoleFactory(
            character_sheet=cls.other_sheet,
            covenant_role=cls.other_role,
        )

    def test_user_sees_their_own_active_assignments(self) -> None:
        """GET list returns assignments on sheets the user currently plays."""
        response = self.client.get("/api/covenants/character-roles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.assignment.pk, ids)

    def test_user_does_not_see_other_users_assignments(self) -> None:
        """Non-staff users cannot see assignments belonging to another player."""
        response = self.client.get("/api/covenants/character-roles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertNotIn(self.other_assignment.pk, ids)

    def test_user_does_not_see_ended_tenures_assignments(self) -> None:
        """Assignments on sheets whose only tenure is ended are not returned."""
        import datetime

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.roster.factories import (
            RosterEntryFactory,
            RosterTenureFactory,
        )

        ended_sheet = CharacterSheetFactory()
        ended_entry = RosterEntryFactory(character_sheet=ended_sheet)
        # Reuse the existing player_data (one PlayerData per account).
        RosterTenureFactory(
            roster_entry=ended_entry,
            player_data=self.player_data,
            end_date=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC),
        )
        ended_role = CovenantRoleFactory(name="RoleViewTest Ended")
        ended_assignment = CharacterCovenantRoleFactory(
            character_sheet=ended_sheet,
            covenant_role=ended_role,
        )
        response = self.client.get("/api/covenants/character-roles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertNotIn(ended_assignment.pk, ids)

    def test_staff_sees_all_assignments(self) -> None:
        """Staff users see all character covenant role assignments."""
        from evennia.accounts.models import AccountDB

        staff_user = AccountDB.objects.create_user(
            username="cov_role_staff",
            email="cov_role_staff@test.com",
            password="staffpass",
            is_staff=True,
        )
        self.client.force_authenticate(user=staff_user)
        response = self.client.get("/api/covenants/character-roles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.assignment.pk, ids)
        self.assertIn(self.other_assignment.pk, ids)

    def test_filter_by_character_sheet(self) -> None:
        """Staff: ?character_sheet=<pk> narrows to assignments on that sheet."""
        from evennia.accounts.models import AccountDB

        staff_user = AccountDB.objects.create_user(
            username="cov_role_staff2",
            email="cov_role_staff2@test.com",
            password="staffpass",
            is_staff=True,
        )
        self.client.force_authenticate(user=staff_user)
        response = self.client.get(
            "/api/covenants/character-roles/",
            {"character_sheet": self.sheet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.assignment.pk, ids)
        self.assertNotIn(self.other_assignment.pk, ids)

    def test_filter_by_is_active_true(self) -> None:
        """?is_active=true returns only rows where left_at is None."""
        import datetime

        from world.covenants.factories import CharacterCovenantRoleFactory

        ended = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant_role=CovenantRoleFactory(name="RoleViewTest Ended2"),
        )
        ended.left_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
        ended.save()

        response = self.client.get("/api/covenants/character-roles/", {"is_active": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data["results"]:
            self.assertIsNone(row["left_at"])

    def test_filter_by_is_active_false(self) -> None:
        """?is_active=false returns only rows where left_at is set."""
        import datetime

        from world.covenants.factories import CharacterCovenantRoleFactory

        ended = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant_role=CovenantRoleFactory(name="RoleViewTest Ended3"),
        )
        ended.left_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
        ended.save()

        response = self.client.get("/api/covenants/character-roles/", {"is_active": "false"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data["results"]:
            self.assertIsNotNone(row["left_at"])

    def test_list_query_count_character_join_does_not_add_per_row(self) -> None:
        """select_related("character_sheet__character") eliminates the OneToOne N+1.

        Before the fix, each serialized membership row fired one extra query to
        traverse character_sheet → character (ObjectDB). With the fix that JOIN is
        done up front; adding more rows must NOT increase the count by more than
        the fixed per-covenant viewer_capabilities overhead (1 query per unique
        covenant, memoized). Character lookups must contribute 0 additional queries.
        We verify this by comparing the query delta for adding 3 extra rows with 3
        extra covenants (max expected delta = 3 viewer_caps + 3 sub_roles + 3
        threads = 9) against the old N+1 path (which would have been 3 additional
        character-lookup queries on top).

        Concretely: delta must be <= 9 (viewer_caps + resolve queries), not 12+
        (viewer_caps + resolve + character lookups).
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.roster.factories import (
            RosterEntryFactory,
            RosterTenureFactory,
        )

        # Force-staff so queryset is unfiltered (avoids tenure filter complexity).
        self.user.is_staff = True
        self.user.save()
        try:
            # Warm up session so session queries are stable.
            self.client.get("/api/covenants/character-roles/")

            with CaptureQueriesContext(connection) as ctx_small:
                response = self.client.get("/api/covenants/character-roles/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            count_small = len(ctx_small.captured_queries)

            # Add 3 extra memberships, each on a distinct covenant + character.
            for i in range(3):
                extra_sheet = CharacterSheetFactory()
                extra_entry = RosterEntryFactory(character_sheet=extra_sheet)
                RosterTenureFactory(
                    roster_entry=extra_entry,
                    player_data=self.player_data,
                    end_date=None,
                )
                CharacterCovenantRoleFactory(
                    character_sheet=extra_sheet,
                    covenant_role=CovenantRoleFactory(name=f"QCRole_{i}"),
                )

            with CaptureQueriesContext(connection) as ctx_large:
                response = self.client.get("/api/covenants/character-roles/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            count_large = len(ctx_large.captured_queries)

            delta = count_large - count_small
            # 3 extra rows × (1 viewer_caps + 1 threads + 1 sub_roles) = 9 max.
            # Without the select_related fix there would be an extra +3 (character
            # lookups). We assert strictly less than 12 to catch any regression.
            self.assertLess(
                delta,
                12,
                f"Query count grew by {delta} for 3 extra rows: "
                f"baseline={count_small}, large={count_large}. "
                "N+1 on character_sheet__character may have regressed.",
            )
        finally:
            self.user.is_staff = False
            self.user.save()

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests receive 403."""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/covenants/character-roles/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_method_not_allowed(self) -> None:
        """Read-only ViewSet: POST returns 405 Method Not Allowed."""
        response = self.client.post(
            "/api/covenants/character-roles/",
            {"character_sheet": self.sheet.pk, "covenant_role": self.role.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class CovenantViewTests(CovenantsViewTestCase):
    """Tests for GET /api/covenants/covenants/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from django.utils import timezone

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        super().setUpTestData()

        # Sheet + active tenure for default user.
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )

        cls.cov_active_member = CovenantFactory(name="MemberCov")
        cls.cov_no_membership = CovenantFactory(name="OutsiderCov")
        cls.cov_dissolved = CovenantFactory(
            name="DissolvedCov",
            covenant_type=CovenantType.BATTLE,
        )
        cls.cov_dissolved.dissolved_at = timezone.now()
        cls.cov_dissolved.save(update_fields=["dissolved_at"])

        # Active membership on cov_active_member.
        cls.role = CovenantRoleFactory(covenant_type=cls.cov_active_member.covenant_type)
        cls.assignment = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.cov_active_member,
            covenant_role=cls.role,
        )

    @tag("postgres")  # serializes legend_total → PG materialized view (#758)
    def test_user_sees_only_active_member_covenant(self) -> None:
        """Non-staff user only sees covenants where they have an active membership."""
        response = self.client.get("/api/covenants/covenants/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.cov_active_member.pk, ids)
        self.assertNotIn(self.cov_no_membership.pk, ids)
        # No membership on dissolved covenant either.
        self.assertNotIn(self.cov_dissolved.pk, ids)

    @tag("postgres")  # serializes legend_total → PG materialized view (#758)
    def test_staff_sees_all(self) -> None:
        """Staff users see all covenants regardless of membership."""
        from evennia.accounts.models import AccountDB

        staff_user = AccountDB.objects.create_user(
            username="cov_view_staff", email="cov_view_staff@test.com", password="p", is_staff=True
        )
        self.client.force_authenticate(user=staff_user)
        response = self.client.get("/api/covenants/covenants/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.cov_active_member.pk, ids)
        self.assertIn(self.cov_no_membership.pk, ids)
        self.assertIn(self.cov_dissolved.pk, ids)

    @tag("postgres")  # serializes legend_total → PG materialized view (#758)
    def test_filter_by_covenant_type(self) -> None:
        """?covenant_type= filters to only covenants of that type."""
        from evennia.accounts.models import AccountDB

        from world.covenants.constants import CovenantType

        staff_user = AccountDB.objects.create_user(
            username="cov_view_staff2",
            email="cov_view_staff2@test.com",
            password="p",
            is_staff=True,
        )
        self.client.force_authenticate(user=staff_user)
        response = self.client.get(
            "/api/covenants/covenants/", {"covenant_type": CovenantType.DURANCE}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data["results"]:
            self.assertEqual(row["covenant_type"], CovenantType.DURANCE)

    @tag("postgres")  # serializes legend_total → PG materialized view (#758)
    def test_filter_by_is_active_true(self) -> None:
        """?is_active=true returns only covenants with dissolved_at=None."""
        from evennia.accounts.models import AccountDB

        staff_user = AccountDB.objects.create_user(
            username="cov_view_staff3",
            email="cov_view_staff3@test.com",
            password="p",
            is_staff=True,
        )
        self.client.force_authenticate(user=staff_user)
        response = self.client.get("/api/covenants/covenants/", {"is_active": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data["results"]:
            self.assertIsNone(row["dissolved_at"])

    @tag("postgres")  # serializes legend_total → PG materialized view (#758)
    def test_serializer_exposes_member_count(self) -> None:
        """Detail endpoint includes member_count reflecting active memberships."""
        response = self.client.get(f"/api/covenants/covenants/{self.cov_active_member.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["member_count"], 1)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests receive 403."""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/covenants/covenants/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_aggregates_member_count_and_legend_without_per_row_queries(self) -> None:
        """List member_count/legend_total come from one bulk pass, not per row (2026-07 audit).

        The legend matview is Postgres-only (absent in the fast SQLite tier), so
        this mocks the bulk legend service — that also isolates the member_count
        aggregate + query-bounding, which need no matview. Adding more covenants
        must not add per-covenant count/legend queries.
        """
        from unittest.mock import patch

        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from evennia.accounts.models import AccountDB
        from evennia.utils.idmapper.models import flush_cache

        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
        )

        staff = AccountDB.objects.create_user(
            username="cov_agg_staff", email="cov_agg_staff@test.com", password="p", is_staff=True
        )
        self.client.force_authenticate(user=staff)
        url = "/api/covenants/covenants/"

        # cov_active_member has one active membership (from setUpTestData).
        legend_map = {self.cov_active_member.pk: 42}

        def fake_totals(ids: list[int]) -> dict[int, int]:
            return {pk: legend_map.get(pk, 0) for pk in ids}

        with patch("world.societies.services.get_covenant_legend_totals", side_effect=fake_totals):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            rows = {row["id"]: row for row in response.data["results"]}
            self.assertEqual(rows[self.cov_active_member.pk]["member_count"], 1)
            self.assertEqual(rows[self.cov_active_member.pk]["legend_total"], 42)
            self.assertEqual(rows[self.cov_no_membership.pk]["member_count"], 0)
            self.assertEqual(rows[self.cov_no_membership.pk]["legend_total"], 0)

            flush_cache()
            with CaptureQueriesContext(connection) as ctx_before:
                self.client.get(url)
            baseline = len(ctx_before.captured_queries)

            # Two more covenants, one with two active members.
            extra = CovenantFactory(name="ExtraCov")
            CharacterCovenantRoleFactory(covenant=extra)
            CharacterCovenantRoleFactory(covenant=extra)
            CovenantFactory(name="ExtraCov2")

            flush_cache()
            with CaptureQueriesContext(connection) as ctx_after:
                after = self.client.get(url)
            self.assertEqual(after.status_code, status.HTTP_200_OK)
            self.assertEqual(len(ctx_after.captured_queries), baseline)
            after_rows = {row["id"]: row for row in after.data["results"]}
            self.assertEqual(after_rows[extra.pk]["member_count"], 2)


class CharacterCovenantRoleSerializerExposureTests(CovenantsViewTestCase):
    """Verify CharacterCovenantRoleSerializer exposes covenant + engaged."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
        )
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        super().setUpTestData()
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )
        cls.cov = CovenantFactory()
        cls.assignment = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.cov,
        )

    def test_serializer_exposes_covenant_and_engaged(self) -> None:
        """Detail endpoint for character-roles includes covenant PK and engaged flag."""
        response = self.client.get(f"/api/covenants/character-roles/{self.assignment.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("covenant", response.data)
        self.assertEqual(response.data["covenant"], self.cov.pk)
        self.assertIn("engaged", response.data)
        self.assertFalse(response.data["engaged"])


@tag("postgres")  # serializes legend_total → societies_covenantlegendsummary (PG view) — #758
class CovenantSerializerLegendAndStorylinesTests(CovenantsViewTestCase):
    """Verify CovenantSerializer detail includes legend_total and storylines."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
        )
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        super().setUpTestData()
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )
        cls.cov = CovenantFactory(name="LegendTestCov")
        cls.assignment = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.cov,
        )

    def test_detail_includes_legend_total(self) -> None:
        """GET /api/covenants/covenants/{pk}/ includes legend_total field."""
        response = self.client.get(f"/api/covenants/covenants/{self.cov.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("legend_total", response.data)
        # No legend credits seeded — should be 0.
        self.assertEqual(response.data["legend_total"], 0)

    def test_detail_includes_storylines(self) -> None:
        """GET /api/covenants/covenants/{pk}/ includes storylines (list of story PKs)."""
        response = self.client.get(f"/api/covenants/covenants/{self.cov.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("storylines", response.data)
        # No stories linked yet — empty list.
        self.assertEqual(response.data["storylines"], [])


class CovenantLevelThresholdViewTests(CovenantsViewTestCase):
    """Tests for GET /api/covenants/level-thresholds/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.covenants.factories import CovenantLevelThresholdFactory

        super().setUpTestData()
        cls.threshold1 = CovenantLevelThresholdFactory(level=1, required_legend=0)
        cls.threshold2 = CovenantLevelThresholdFactory(level=2, required_legend=100)

    def test_list_returns_thresholds(self) -> None:
        """GET list returns seeded threshold rows."""
        response = self.client.get("/api/covenants/level-thresholds/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        levels = [row["level"] for row in response.data]
        self.assertIn(1, levels)
        self.assertIn(2, levels)

    def test_response_shape(self) -> None:
        """Each threshold row exposes level and required_legend."""
        response = self.client.get("/api/covenants/level-thresholds/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data:
            self.assertIn("level", row)
            self.assertIn("required_legend", row)

    def test_ordered_by_level(self) -> None:
        """Thresholds are returned in ascending level order."""
        response = self.client.get("/api/covenants/level-thresholds/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        levels = [row["level"] for row in response.data]
        self.assertEqual(levels, sorted(levels))

    def test_no_pagination(self) -> None:
        """Response is a plain list (not paginated with results/count wrapper)."""
        response = self.client.get("/api/covenants/level-thresholds/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_post_not_allowed(self) -> None:
        """Read-only endpoint: POST returns 405."""
        response = self.client.post(
            "/api/covenants/level-thresholds/",
            {"level": 99, "required_legend": 9999},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests receive 403."""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/covenants/level-thresholds/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CovenantRoleViewTests(CovenantsViewTestCase):
    """Tests for GET /api/covenants/roles/ including the parent_role filter."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from world.covenants.factories import SubroleCovenantRoleFactory

        cls.parent_role = CovenantRoleFactory(name="RoleFilter Parent")
        cls.sub_a = SubroleCovenantRoleFactory(name="RoleFilter Sub A", parent_role=cls.parent_role)
        cls.sub_b = SubroleCovenantRoleFactory(name="RoleFilter Sub B", parent_role=cls.parent_role)
        cls.other_parent = CovenantRoleFactory(name="RoleFilter Other Parent")
        cls.other_sub = SubroleCovenantRoleFactory(
            name="RoleFilter Other Sub", parent_role=cls.other_parent
        )

    def test_list_exposes_parent_role(self) -> None:
        """The serializer exposes parent_role so sub-roles are identifiable."""
        response = self.client.get(f"/api/covenants/roles/?parent_role={self.parent_role.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data:
            self.assertIn("parent_role", row)

    def test_filter_by_parent_role_returns_only_its_subroles(self) -> None:
        """?parent_role=<id> returns exactly that role's sub-roles."""
        response = self.client.get(f"/api/covenants/roles/?parent_role={self.parent_role.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {row["id"] for row in response.data}
        self.assertEqual(returned_ids, {self.sub_a.pk, self.sub_b.pk})
        for row in response.data:
            self.assertEqual(row["parent_role"], self.parent_role.pk)

    def test_is_leadership_absent_from_role_payload(self) -> None:
        """The CovenantRoleSerializer must NOT expose is_leadership (#1027)."""
        response = self.client.get(f"/api/covenants/roles/{self.parent_role.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("is_leadership", response.data)


class CovenantRoleTechniqueSpecialtyFieldTests(CovenantsViewTestCase):
    """Tests for CovenantRoleSerializer's nested technique_specialties field (#2443)."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from world.covenants.factories import CovenantRoleTechniqueSpecialtyFactory
        from world.magic.constants import TechniqueFunction

        cls.role = CovenantRoleFactory(name="Specialty Role")
        cls.specialty = CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=cls.role,
            function=TechniqueFunction.CHARM,
            multiplier_tenths=15,
        )

    def test_role_payload_includes_technique_specialties(self) -> None:
        """The role payload exposes a technique_specialties list."""
        response = self.client.get(f"/api/covenants/roles/{self.role.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("technique_specialties", response.data)
        self.assertEqual(len(response.data["technique_specialties"]), 1)

    def test_technique_specialty_row_shape(self) -> None:
        """Each row exposes function, function_display, and multiplier_tenths."""
        response = self.client.get(f"/api/covenants/roles/{self.role.pk}/")
        row = response.data["technique_specialties"][0]
        self.assertEqual(row["function"], "charm")
        self.assertEqual(row["function_display"], "Charm")
        self.assertEqual(row["multiplier_tenths"], 15)

    def test_role_without_specialties_returns_empty_list(self) -> None:
        """A role with no CovenantRoleTechniqueSpecialty rows returns an empty list."""
        bare_role = CovenantRoleFactory(name="Bare Role")
        response = self.client.get(f"/api/covenants/roles/{bare_role.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["technique_specialties"], [])


class CharacterCovenantRoleRankFieldTests(CovenantsViewTestCase):
    """Verify the membership serializer exposes rank and viewer_capabilities."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
        )
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        super().setUpTestData()
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )
        cls.cov = CovenantFactory(name="RankFieldTestCov")
        cls.mgr_rank = CovenantManagerRankFactory(covenant=cls.cov, tier=1)
        cls.assignment = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.cov,
            rank=cls.mgr_rank,
        )

    def test_membership_payload_includes_rank(self) -> None:
        """GET character-roles/{pk}/ includes a nested rank block."""
        response = self.client.get(f"/api/covenants/character-roles/{self.assignment.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("rank", response.data)
        self.assertEqual(response.data["rank"]["id"], self.mgr_rank.pk)
        self.assertIn("name", response.data["rank"])
        self.assertIn("tier", response.data["rank"])

    def test_membership_payload_includes_viewer_capabilities(self) -> None:
        """GET character-roles/{pk}/ includes viewer_capabilities for the requesting user."""
        response = self.client.get(f"/api/covenants/character-roles/{self.assignment.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("viewer_capabilities", response.data)
        caps = response.data["viewer_capabilities"]
        self.assertIn("can_invite", caps)
        self.assertIn("can_kick", caps)
        self.assertIn("can_manage_ranks", caps)
        self.assertIn("can_request_gm", caps)
        # The user's own rank is the manager rank — all caps True.
        self.assertTrue(caps["can_invite"])
        self.assertTrue(caps["can_kick"])
        self.assertTrue(caps["can_manage_ranks"])
        self.assertTrue(caps["can_request_gm"])

    def test_is_leadership_absent_from_membership_payload(self) -> None:
        """The CharacterCovenantRoleSerializer must NOT expose is_leadership."""
        response = self.client.get(f"/api/covenants/character-roles/{self.assignment.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check nested covenant_role block too.
        self.assertNotIn("is_leadership", response.data)
        self.assertNotIn("is_leadership", response.data.get("covenant_role", {}))


class CovenantRankViewSetTests(CovenantsViewTestCase):
    """Tests for /api/covenants/ranks/ CRUD and custom actions."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
            CovenantRankFactory,
        )
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        super().setUpTestData()

        # Manager user + sheet + active tenure.
        cls.mgr_sheet = CharacterSheetFactory()
        cls.mgr_entry = RosterEntryFactory(character_sheet=cls.mgr_sheet)
        cls.mgr_player_data = PlayerDataFactory(account=cls.user)
        cls.mgr_tenure = RosterTenureFactory(
            roster_entry=cls.mgr_entry,
            player_data=cls.mgr_player_data,
            end_date=None,
        )

        # Non-manager user.
        cls.non_mgr_user = AccountDB.objects.create_user(
            username="ranktestnonmgr",
            email="ranktestnonmgr@test.com",
            password="p",
        )
        cls.non_mgr_sheet = CharacterSheetFactory()
        cls.non_mgr_entry = RosterEntryFactory(character_sheet=cls.non_mgr_sheet)
        cls.non_mgr_player = PlayerDataFactory(account=cls.non_mgr_user)
        cls.non_mgr_tenure = RosterTenureFactory(
            roster_entry=cls.non_mgr_entry,
            player_data=cls.non_mgr_player,
            end_date=None,
        )

        cls.cov = CovenantFactory(name="RankViewSetCov")
        cls.mgr_rank = CovenantManagerRankFactory(covenant=cls.cov, tier=1)
        cls.member_rank = CovenantRankFactory(
            covenant=cls.cov, tier=2, can_invite=False, can_kick=False, can_manage_ranks=False
        )

        # Manager membership on the test covenant.
        cls.mgr_membership = CharacterCovenantRoleFactory(
            character_sheet=cls.mgr_sheet,
            covenant=cls.cov,
            rank=cls.mgr_rank,
        )
        # Non-manager membership on the test covenant.
        cls.non_mgr_membership = CharacterCovenantRoleFactory(
            character_sheet=cls.non_mgr_sheet,
            covenant=cls.cov,
            rank=cls.member_rank,
        )

    def _non_mgr_client(self) -> "APIClient":
        client = APIClient()
        client.force_authenticate(user=self.non_mgr_user)
        return client

    def test_list_returns_ranks_for_member(self) -> None:
        """GET /api/covenants/ranks/ returns ranks the user's covenant has."""
        response = self.client.get("/api/covenants/ranks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.mgr_rank.pk, ids)
        self.assertIn(self.member_rank.pk, ids)

    def test_filter_by_covenant(self) -> None:
        """?covenant=<pk> narrows to ranks for that covenant."""
        response = self.client.get("/api/covenants/ranks/", {"covenant": self.cov.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data["results"]:
            self.assertEqual(row["covenant"], self.cov.pk)

    def test_manager_can_create_rank(self) -> None:
        """A manager (can_manage_ranks=True) can POST a new rank."""
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
        )

        new_cov = CovenantFactory(name="RankCreateCov")
        mgr_rank = CovenantManagerRankFactory(covenant=new_cov, tier=1)
        CharacterCovenantRoleFactory(
            character_sheet=self.mgr_sheet,
            covenant=new_cov,
            rank=mgr_rank,
        )
        response = self.client.post(
            "/api/covenants/ranks/",
            {
                "covenant": new_cov.pk,
                "name": "Scribe",
                "tier": 3,
                "can_invite": False,
                "can_kick": False,
                "can_manage_ranks": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Scribe")
        self.assertEqual(response.data["tier"], 3)

    def test_manager_can_create_rank_with_can_lead_rituals(self) -> None:
        """A manager can POST a new rank with can_lead_rituals set."""
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
        )

        new_cov = CovenantFactory(name="RankLeadRitualsCov")
        mgr_rank = CovenantManagerRankFactory(covenant=new_cov, tier=1)
        CharacterCovenantRoleFactory(
            character_sheet=self.mgr_sheet,
            covenant=new_cov,
            rank=mgr_rank,
        )
        response = self.client.post(
            "/api/covenants/ranks/",
            {
                "covenant": new_cov.pk,
                "name": "Ritual Leader",
                "tier": 3,
                "can_lead_rituals": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["can_lead_rituals"])

    def test_non_manager_cannot_create_rank(self) -> None:
        """A member without can_manage_ranks is denied with 403."""
        client = self._non_mgr_client()
        response = client.post(
            "/api/covenants/ranks/",
            {
                "covenant": self.cov.pk,
                "name": "Infiltrator",
                "tier": 5,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_rename_rank(self) -> None:
        """PATCH a rank name succeeds for a manager."""
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
            CovenantRankFactory,
        )

        cov2 = CovenantFactory(name="RankRenameCov")
        mgr_rank2 = CovenantManagerRankFactory(covenant=cov2, tier=1)
        target_rank = CovenantRankFactory(covenant=cov2, tier=2, name="OldName")
        CharacterCovenantRoleFactory(
            character_sheet=self.mgr_sheet,
            covenant=cov2,
            rank=mgr_rank2,
        )
        # Add a second member so covenant doesn't dissolve.
        CharacterCovenantRoleFactory(
            character_sheet=self.non_mgr_sheet,
            covenant=cov2,
            rank=target_rank,
        )
        response = self.client.patch(
            f"/api/covenants/ranks/{target_rank.pk}/",
            {"name": "NewName"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "NewName")

    def test_non_manager_cannot_update_rank(self) -> None:
        """PATCH denied (403) for a member without can_manage_ranks."""
        client = self._non_mgr_client()
        response = client.patch(
            f"/api/covenants/ranks/{self.member_rank.pk}/",
            {"name": "Hacker"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reorder_action(self) -> None:
        """POST /api/covenants/ranks/reorder/ reorders the ladder."""
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
            CovenantRankFactory,
        )

        cov3 = CovenantFactory(name="ReorderCov")
        r1 = CovenantManagerRankFactory(covenant=cov3, tier=1, name="Leader")
        r2 = CovenantRankFactory(covenant=cov3, tier=2, name="Mid")
        r3 = CovenantRankFactory(covenant=cov3, tier=3, name="Base")
        CharacterCovenantRoleFactory(
            character_sheet=self.mgr_sheet,
            covenant=cov3,
            rank=r1,
        )
        # Non-mgr as second member so covenant persists.
        CharacterCovenantRoleFactory(
            character_sheet=self.non_mgr_sheet,
            covenant=cov3,
            rank=r3,
        )
        # Reverse order: r3 → tier 1, r2 → tier 2, r1 → tier 3.
        response = self.client.post(
            "/api/covenants/ranks/reorder/",
            {"covenant": cov3.pk, "ordered_rank_ids": [r3.pk, r2.pk, r1.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tiers = {row["id"]: row["tier"] for row in response.data}
        self.assertEqual(tiers[r3.pk], 1)
        self.assertEqual(tiers[r2.pk], 2)
        self.assertEqual(tiers[r1.pk], 3)

    def test_assign_member_action(self) -> None:
        """POST /api/covenants/ranks/{pk}/assign-member/ re-assigns a membership's rank."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
            CovenantRankFactory,
        )

        cov4 = CovenantFactory(name="AssignMemberCov")
        top = CovenantManagerRankFactory(covenant=cov4, tier=1, name="Top")
        base = CovenantRankFactory(covenant=cov4, tier=2, name="Base")
        CharacterCovenantRoleFactory(character_sheet=self.mgr_sheet, covenant=cov4, rank=top)
        target_m = CharacterCovenantRoleFactory(
            character_sheet=CharacterSheetFactory(), covenant=cov4, rank=base
        )
        response = self.client.post(
            f"/api/covenants/ranks/{top.pk}/assign-member/",
            {"membership": target_m.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target_m.refresh_from_db()
        self.assertEqual(target_m.rank_id, top.pk)

    def test_transfer_top_action_success(self) -> None:
        """POST transfer-top/ — manager transfers top rank to another active member (200)."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
            CovenantRankFactory,
        )

        cov5 = CovenantFactory(name="TransferTopCov")
        top_rank = CovenantManagerRankFactory(covenant=cov5, tier=1, name="Leader")
        base_rank = CovenantRankFactory(covenant=cov5, tier=2, name="Base")
        mgr_m = CharacterCovenantRoleFactory(
            character_sheet=self.mgr_sheet, covenant=cov5, rank=top_rank
        )
        recipient_m = CharacterCovenantRoleFactory(
            character_sheet=CharacterSheetFactory(), covenant=cov5, rank=base_rank
        )
        response = self.client.post(
            f"/api/covenants/ranks/{top_rank.pk}/transfer-top/",
            {"new_top_membership": recipient_m.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recipient_m.refresh_from_db()
        mgr_m.refresh_from_db()
        self.assertEqual(recipient_m.rank_id, top_rank.pk)
        self.assertEqual(mgr_m.rank_id, base_rank.pk)

    def test_transfer_top_non_manager_denied(self) -> None:
        """POST transfer-top/ by a member without can_manage_ranks is denied with 403."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
            CovenantRankFactory,
        )

        cov6 = CovenantFactory(name="TransferTopDeniedCov")
        top_rank = CovenantManagerRankFactory(covenant=cov6, tier=1, name="Leader6")
        base_rank = CovenantRankFactory(covenant=cov6, tier=2, name="Base6")
        CharacterCovenantRoleFactory(character_sheet=self.mgr_sheet, covenant=cov6, rank=top_rank)
        # non_mgr_sheet must be a member so the non-manager can see the rank via get_queryset.
        CharacterCovenantRoleFactory(
            character_sheet=self.non_mgr_sheet, covenant=cov6, rank=base_rank
        )
        recipient_m = CharacterCovenantRoleFactory(
            character_sheet=CharacterSheetFactory(), covenant=cov6, rank=base_rank
        )
        client = self._non_mgr_client()
        response = client.post(
            f"/api/covenants/ranks/{top_rank.pk}/transfer-top/",
            {"new_top_membership": recipient_m.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_denied(self) -> None:
        """Unauthenticated requests receive 403."""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/covenants/ranks/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InductionDraftAuthzApiTests(TestCase):
    """POST /api/magic/rituals/sessions/ maps CovenantError → 400 for induction gate.

    Verifies that a character without can_invite cannot bypass the
    assert_initiator_can_induct gate via the generic draft endpoint.
    """

    def _make_authenticated_client_with_sheet(self) -> tuple:
        """Return (client, initiator_sheet) for a user with an active character.

        Creates an AccountDB → PlayerData → RosterTenure → RosterEntry →
        CharacterSheet chain so the serializer's for_account() lookup
        resolves the initiator from request.user.
        """
        from evennia.accounts.models import AccountDB

        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        account = AccountDB.objects.create_user(
            username=f"induct_test_{id(self)}",
            email=f"induct_{id(self)}@test.com",
            password="testpass123",
        )
        sheet = CharacterSheetFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet)
        player_data = PlayerDataFactory(account=account)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=player_data,
            end_date=None,
        )
        client = APIClient()
        client.force_authenticate(user=account)
        return client, sheet

    def _build_request_body(self, *, ritual, invitee_sheet, covenant) -> dict:
        """Build the POST body for drafting a covenant induction session."""
        return {
            "ritual_id": ritual.pk,
            "invitee_ids": [invitee_sheet.pk],
            "session_references": [{"kind": "COVENANT", "ref_covenant_id": covenant.pk}],
        }

    def test_generic_endpoint_blocks_non_can_invite_initiator(self) -> None:
        """A member without can_invite gets HTTP 400 from the draft endpoint."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRankFactory,
        )
        from world.magic.factories import CovenantInductionRitualFactory

        client, initiator_sheet = self._make_authenticated_client_with_sheet()
        cov = CovenantFactory()
        # Initiator is a member but rank has can_invite=False.
        CharacterCovenantRoleFactory(
            character_sheet=initiator_sheet,
            covenant=cov,
            rank=CovenantRankFactory(covenant=cov, can_invite=False),
        )
        candidate = CharacterSheetFactory()
        ritual = CovenantInductionRitualFactory()

        response = client.post(
            "/api/magic/rituals/sessions/",
            self._build_request_body(ritual=ritual, invitee_sheet=candidate, covenant=cov),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("permission to invite", response.data["detail"])

    def test_generic_endpoint_allows_can_invite_initiator(self) -> None:
        """A member with can_invite=True gets HTTP 201 from the draft endpoint."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantManagerRankFactory,
        )
        from world.magic.factories import CovenantInductionRitualFactory

        client, initiator_sheet = self._make_authenticated_client_with_sheet()
        cov = CovenantFactory()
        # Initiator is a manager (can_invite=True).
        CharacterCovenantRoleFactory(
            character_sheet=initiator_sheet,
            covenant=cov,
            rank=CovenantManagerRankFactory(covenant=cov),
        )
        candidate = CharacterSheetFactory()
        ritual = CovenantInductionRitualFactory()

        response = client.post(
            "/api/magic/rituals/sessions/",
            self._build_request_body(ritual=ritual, invitee_sheet=candidate, covenant=cov),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

"""Tests for covenants API views."""

from django.test import TestCase
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

    def test_user_sees_only_active_member_covenant(self) -> None:
        """Non-staff user only sees covenants where they have an active membership."""
        response = self.client.get("/api/covenants/covenants/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.cov_active_member.pk, ids)
        self.assertNotIn(self.cov_no_membership.pk, ids)
        # No membership on dissolved covenant either.
        self.assertNotIn(self.cov_dissolved.pk, ids)

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

"""API tests for the Lab station REST surface (#1234).

Covers ``LabStationViewSet`` — status (GET), install (POST, detail=False),
upgrade (POST, detail=False, separate route from install per the fixed
alias defect), and repair (POST, detail=True). All write endpoints converge
on ``Action().run()`` (``StartRoomFeatureProjectAction`` /
``RepairLabStationAction``, actions/definitions/room_features.py) —
mirrors ``world/magic/tests/test_sanctum_viewset.py``'s HTTP-contract style
but drives the real action/service stack rather than mocking it, since the
underlying services are already unit-tested in
``test_lab_station_repair.py`` / ``test_lab_station_progression.py``.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.models import LabStationDetails
from world.locations.factories import LocationOwnershipFactory
from world.projects.models import Project
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class LabStationApiTestCase(TestCase):
    """Base test-case: owner account/character/sheet with standing over a room."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = AccountFactory(username="lab_station_api_owner")
        cls.owner_char = CharacterFactory(db_key="lab_station_api_owner_char")
        cls.owner_sheet = CharacterSheetFactory(character=cls.owner_char)
        owner_entry = RosterEntryFactory(character_sheet=cls.owner_sheet)
        RosterTenureFactory(
            roster_entry=owner_entry,
            player_data=PlayerDataFactory(account=cls.owner),
        )

        cls.room_profile = RoomProfileFactory()
        cls.owner_char.location = cls.room_profile.objectdb
        cls.owner_char.save()
        LocationOwnershipFactory(
            on_room=True,
            room_profile=cls.room_profile,
            holder_persona=cls.owner_sheet.primary_persona,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)


class LabStationInstallTests(LabStationApiTestCase):
    """POST /api/items/lab-stations/install/ — detail=False."""

    def test_install_creates_project(self) -> None:
        response = self.client.post(
            "/api/items/lab-stations/install/",
            {"room_profile_id": self.room_profile.pk, "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn("project_id", response.data)
        self.assertTrue(Project.objects.filter(pk=response.data["project_id"]).exists())

    def test_install_rejects_bad_body_with_400(self) -> None:
        response = self.client.post(
            "/api/items/lab-stations/install/",
            {"room_profile_id": self.room_profile.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_install_without_standing_returns_400(self) -> None:
        other_room = RoomProfileFactory()
        response = self.client.post(
            "/api/items/lab-stations/install/",
            {"room_profile_id": other_room.pk, "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)


class LabStationUpgradeTests(LabStationApiTestCase):
    """POST /api/items/lab-stations/upgrade/ — a real, separate route from install."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        cls.instance = RoomFeatureInstanceFactory(
            room_profile=cls.room_profile, feature_kind=cls.kind, level=1
        )
        LabStationDetails.objects.create(
            feature_instance=cls.instance, durability=20, max_durability=20
        )

    def test_upgrade_creates_project_at_higher_level(self) -> None:
        response = self.client.post(
            "/api/items/lab-stations/upgrade/",
            {"room_profile_id": self.room_profile.pk, "target_level": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn("project_id", response.data)

    def test_upgrade_rejects_non_higher_level_with_400(self) -> None:
        response = self.client.post(
            "/api/items/lab-stations/upgrade/",
            {"room_profile_id": self.room_profile.pk, "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LabStationRepairTests(LabStationApiTestCase):
    """POST /api/items/lab-stations/<id>/repair/ + GET .../<id>/ status."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        cls.instance = RoomFeatureInstanceFactory(
            room_profile=cls.room_profile, feature_kind=cls.kind, level=2
        )
        cls.station = LabStationDetails.objects.create(
            feature_instance=cls.instance, durability=10, max_durability=40
        )

    def setUp(self) -> None:
        super().setUp()
        from world.currency.services import get_or_create_purse

        purse = get_or_create_purse(self.owner_sheet)
        purse.balance = 10_000
        purse.save(update_fields=["balance"])
        # setUpTestData's self.station is a class-level shared object; a prior
        # test's refresh_from_db() would otherwise leak its mutated in-memory
        # durability into this test even though the DB itself rolls back
        # between tests (Django TestCase per-test transaction wrapping).
        self.station.refresh_from_db()

    def test_repair_endpoint(self) -> None:
        response = self.client.post(
            f"/api/items/lab-stations/{self.station.feature_instance_id}/repair/",
            {"restore_points": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("durability", response.data)
        self.station.refresh_from_db()
        self.assertEqual(response.data["durability"], self.station.durability)

    def test_repair_rejects_bad_body_with_400(self) -> None:
        response = self.client.post(
            f"/api/items/lab-stations/{self.station.feature_instance_id}/repair/",
            {"restore_points": 0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_status_endpoint(self) -> None:
        response = self.client.get(f"/api/items/lab-stations/{self.station.feature_instance_id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["durability"], self.station.durability)
        self.assertEqual(response.data["max_durability"], self.station.max_durability)
        self.assertEqual(response.data["level"], self.instance.level)
        self.assertFalse(response.data["is_broken"])

    def test_status_endpoint_unknown_station_returns_404(self) -> None:
        response = self.client.get("/api/items/lab-stations/999999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class LabStationActorResolutionTests(LabStationApiTestCase):
    """Alt-guard coverage for ``LabStationViewSet._resolve_actor`` (review finding).

    An account may have more than one simultaneously-active character (alts).
    ``_resolve_actor`` must not silently guess which one is acting via
    ``RosterEntry.objects.for_account(...).first()`` — it now delegates to the
    shared ``world.magic.services.auth._resolve_actor_sheet`` alt-guard, which
    raises rather than picking arbitrarily when more than one active tenure exists.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # A second, simultaneously-active character on the SAME account — no
        # standing over cls.room_profile (no LocationOwnership row for it).
        cls.alt_char = CharacterFactory(db_key="lab_station_api_owner_alt_char")
        cls.alt_sheet = CharacterSheetFactory(character=cls.alt_char)
        alt_entry = RosterEntryFactory(character_sheet=cls.alt_sheet)
        RosterTenureFactory(
            roster_entry=alt_entry,
            player_data=cls.owner.player_data,
        )

    def test_install_with_multiple_active_tenures_and_no_actor_sheet_id_fails_safe(self) -> None:
        """No ``actor_sheet_id`` + 2 active tenures on the account → 400, never guesses."""
        response = self.client.post(
            "/api/items/lab-stations/install/",
            {"room_profile_id": self.room_profile.pk, "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("actor_sheet_id", str(response.data))
        self.assertFalse(Project.objects.exists())

    def test_install_with_explicit_actor_sheet_id_for_standing_character_succeeds(self) -> None:
        """Explicit ``actor_sheet_id`` naming the standing character → 201."""
        response = self.client.post(
            "/api/items/lab-stations/install/",
            {
                "room_profile_id": self.room_profile.pk,
                "target_level": 1,
                "actor_sheet_id": self.owner_sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_install_with_explicit_actor_sheet_id_for_non_standing_alt_returns_400(self) -> None:
        """Explicit ``actor_sheet_id`` naming the non-standing alt → 400, not a guess."""
        response = self.client.post(
            "/api/items/lab-stations/install/",
            {
                "room_profile_id": self.room_profile.pk,
                "target_level": 1,
                "actor_sheet_id": self.alt_sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("standing", str(response.data).lower())


class LabStationNoActiveCharacterTests(TestCase):
    """No-active-tenure guard — previously zero test coverage (review finding).

    One route (install) is enough to cover the shared ``_resolve_actor`` guard;
    all three write routes call the same method.
    """

    def setUp(self) -> None:
        self.account = AccountFactory(username="lab_station_api_no_tenure")
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_install_with_no_active_character_returns_403(self) -> None:
        response = self.client.post(
            "/api/items/lab-stations/install/",
            {"room_profile_id": 1, "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

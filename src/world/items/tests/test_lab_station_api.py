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

    def setUp(self) -> None:
        self.owner = AccountFactory(username="lab_station_api_owner")
        self.owner_char = CharacterFactory(db_key="lab_station_api_owner_char")
        self.owner_sheet = CharacterSheetFactory(character=self.owner_char)
        owner_entry = RosterEntryFactory(character_sheet=self.owner_sheet)
        RosterTenureFactory(
            roster_entry=owner_entry,
            player_data=PlayerDataFactory(account=self.owner),
        )

        self.room_profile = RoomProfileFactory()
        self.owner_char.location = self.room_profile.objectdb
        self.owner_char.save()
        LocationOwnershipFactory(
            on_room=True,
            room_profile=self.room_profile,
            holder_persona=self.owner_sheet.primary_persona,
        )

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

    def setUp(self) -> None:
        super().setUp()
        self.kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        self.instance = RoomFeatureInstanceFactory(
            room_profile=self.room_profile, feature_kind=self.kind, level=1
        )
        LabStationDetails.objects.create(
            feature_instance=self.instance, durability=20, max_durability=20
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

    def setUp(self) -> None:
        super().setUp()
        self.kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        self.instance = RoomFeatureInstanceFactory(
            room_profile=self.room_profile, feature_kind=self.kind, level=2
        )
        self.station = LabStationDetails.objects.create(
            feature_instance=self.instance, durability=10, max_durability=40
        )

        from world.currency.services import get_or_create_purse

        purse = get_or_create_purse(self.owner_sheet)
        purse.balance = 10_000
        purse.save(update_fields=["balance"])

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


class LabStationListTests(LabStationApiTestCase):
    """GET /api/items/lab-stations/ — pagination + room filter (#1234 review finding).

    ``LabStationViewSet`` previously had no ``pagination_class``/
    ``filter_backends``, so this list endpoint returned every
    ``LabStationDetails`` row in the game unbounded to any authenticated user.
    """

    def setUp(self) -> None:
        super().setUp()
        self.kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        self.instance = RoomFeatureInstanceFactory(
            room_profile=self.room_profile, feature_kind=self.kind, level=1
        )
        self.station = LabStationDetails.objects.create(
            feature_instance=self.instance, durability=20, max_durability=20
        )
        self.other_room = RoomProfileFactory()
        self.other_kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.COMMAND_CENTER
        )
        self.other_instance = RoomFeatureInstanceFactory(
            room_profile=self.other_room, feature_kind=self.other_kind, level=1
        )
        self.other_station = LabStationDetails.objects.create(
            feature_instance=self.other_instance, durability=5, max_durability=20
        )

    def test_list_is_paginated(self) -> None:
        response = self.client.get("/api/items/lab-stations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 2)

    def test_list_filters_by_room_profile(self) -> None:
        response = self.client.get(
            "/api/items/lab-stations/", {"room_profile": self.room_profile.pk}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["durability"], self.station.durability)

    def test_list_filters_to_other_room_excludes_first_station(self) -> None:
        response = self.client.get("/api/items/lab-stations/", {"room_profile": self.other_room.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["durability"], self.other_station.durability)


class LabStationActorResolutionTests(LabStationApiTestCase):
    """Alt-guard coverage for ``LabStationViewSet._resolve_actor`` (review finding).

    An account may have more than one simultaneously-active character (alts).
    ``_resolve_actor`` must not silently guess which one is acting via
    ``RosterEntry.objects.for_account(...).first()`` — it now delegates to the
    shared ``world.magic.services.auth._resolve_actor_sheet`` alt-guard, which
    raises rather than picking arbitrarily when more than one active tenure exists.
    """

    def setUp(self) -> None:
        super().setUp()
        # A second, simultaneously-active character on the SAME account — no
        # standing over self.room_profile (no LocationOwnership row for it).
        self.alt_char = CharacterFactory(db_key="lab_station_api_owner_alt_char")
        self.alt_sheet = CharacterSheetFactory(character=self.alt_char)
        alt_entry = RosterEntryFactory(character_sheet=self.alt_sheet)
        RosterTenureFactory(
            roster_entry=alt_entry,
            player_data=self.owner.player_data,
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

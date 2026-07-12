"""Tests for the #2177 defense web surfaces.

Covers ``DefenseInstallViewSet`` (install/upgrade/fund-ward, POST) and the
three read-only status viewsets (``ExitBarsViewSet``/``RoomWardViewSet``/
``RoomAlarmViewSet``). All write endpoints converge on ``Action().run()``
(``StartDefenseInstallationAction``/``FundRoomWardAction``,
``actions/definitions/room_features.py``) -- mirrors
``world/items/tests/test_lab_station_api.py``'s HTTP-contract style and its
exact authentication fixture (owner account/character/sheet + roster tenure
+ ``LocationOwnership`` standing), not the placeholder ``account.puppet=``
fixture originally sketched in the plan.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from evennia_extensions.models import ExitProfile
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.factories import LocationOwnershipFactory
from world.magic.factories import ResonanceFactory
from world.projects.models import Project
from world.room_features.models import ExitBarsDetails, RoomAlarmDetails, RoomWardDetails
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class DefenseApiTestCase(TestCase):
    """Base test-case: owner account/character/sheet with standing over a room."""

    def setUp(self) -> None:
        self.owner = AccountFactory(username="defense_api_owner")
        self.owner_char = CharacterFactory(db_key="defense_api_owner_char")
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


class DefenseInstallTests(DefenseApiTestCase):
    """POST /api/room-features/defenses/install/ — detail=False."""

    def test_install_alarm_via_api(self) -> None:
        response = self.client.post(
            "/api/room-features/defenses/install/",
            {"defense_kind": "ROOM_ALARM", "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn("project_id", response.data)
        self.assertTrue(Project.objects.filter(pk=response.data["project_id"]).exists())

    def test_install_rejects_bad_body_with_400(self) -> None:
        response = self.client.post(
            "/api/room-features/defenses/install/",
            {"defense_kind": "ROOM_ALARM"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_install_bars_without_exit_id_returns_400(self) -> None:
        response = self.client.post(
            "/api/room-features/defenses/install/",
            {"defense_kind": "EXIT_BARS", "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_install_ward_without_resonance_returns_400(self) -> None:
        response = self.client.post(
            "/api/room-features/defenses/install/",
            {"defense_kind": "ROOM_WARD", "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_install_ward_with_resonance_succeeds(self) -> None:
        resonance = ResonanceFactory()
        response = self.client.post(
            "/api/room-features/defenses/install/",
            {"defense_kind": "ROOM_WARD", "target_level": 1, "resonance_id": resonance.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn("project_id", response.data)


class DefenseUpgradeTests(DefenseApiTestCase):
    """POST /api/room-features/defenses/upgrade/ — a real, separate route from install."""

    def test_upgrade_route_dispatches_same_action(self) -> None:
        response = self.client.post(
            "/api/room-features/defenses/upgrade/",
            {"defense_kind": "ROOM_ALARM", "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class FundWardTests(DefenseApiTestCase):
    """POST /api/room-features/defenses/fund-ward/."""

    def setUp(self) -> None:
        super().setUp()
        from world.magic.models.aura import CharacterResonance

        self.resonance = ResonanceFactory()
        self.ward = RoomWardDetails.objects.create(
            room_profile=self.room_profile, resonance=self.resonance, resonance_reserve=0
        )
        self.cr = CharacterResonance.objects.create(
            character_sheet=self.owner_sheet, resonance=self.resonance, balance=100
        )

    def test_fund_ward_via_api(self) -> None:
        response = self.client.post(
            "/api/room-features/defenses/fund-ward/",
            {"amount": 10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["resonance_reserve"], 10)
        self.ward.refresh_from_db()
        self.assertEqual(self.ward.resonance_reserve, 10)

    def test_fund_ward_insufficient_resonance_returns_400(self) -> None:
        response = self.client.post(
            "/api/room-features/defenses/fund-ward/",
            {"amount": 1000},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ExitBarsStatusTests(DefenseApiTestCase):
    """GET /api/room-features/exit-bars/."""

    def setUp(self) -> None:
        super().setUp()
        self.dest = ObjectDBFactory(
            db_key="DefenseDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.exit_obj = ObjectDBFactory(db_key="north", db_typeclass_path="typeclasses.exits.Exit")
        self.exit_obj.location = self.room_profile.objectdb
        self.exit_obj.destination = self.dest
        self.exit_obj.save()
        self.exit_profile = ExitProfile.get_or_create_for_exit(self.exit_obj)
        self.bars = ExitBarsDetails.objects.create(exit_profile=self.exit_profile, level=2)

    def test_status_endpoint(self) -> None:
        response = self.client.get(f"/api/room-features/exit-bars/{self.exit_profile.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["level"], 2)

    def test_list_endpoint(self) -> None:
        response = self.client.get("/api/room-features/exit-bars/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class RoomWardStatusTests(DefenseApiTestCase):
    """GET /api/room-features/room-wards/."""

    def setUp(self) -> None:
        super().setUp()
        self.resonance = ResonanceFactory()
        self.ward = RoomWardDetails.objects.create(
            room_profile=self.room_profile, resonance=self.resonance, level=1
        )

    def test_status_endpoint(self) -> None:
        response = self.client.get(f"/api/room-features/room-wards/{self.room_profile.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["level"], 1)


class RoomAlarmStatusTests(DefenseApiTestCase):
    """GET /api/room-features/room-alarms/."""

    def setUp(self) -> None:
        super().setUp()
        self.alarm = RoomAlarmDetails.objects.create(room_profile=self.room_profile, level=1)

    def test_status_endpoint(self) -> None:
        response = self.client.get(f"/api/room-features/room-alarms/{self.room_profile.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["level"], 1)


class DefenseNoActiveCharacterTests(TestCase):
    """No-active-tenure guard — mirrors ``LabStationNoActiveCharacterTests``."""

    def setUp(self) -> None:
        self.account = AccountFactory(username="defense_api_no_tenure")
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_install_with_no_active_character_returns_403(self) -> None:
        response = self.client.post(
            "/api/room-features/defenses/install/",
            {"defense_kind": "ROOM_ALARM", "target_level": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

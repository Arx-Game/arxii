"""Tests for ShipViewSet / ShipTypeViewSet — the read "My Ships" API (#1832 Task 10)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CovenantFactory
from world.locations.services import transfer_ownership
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.ships.factories import ShipDetailsFactory, ShipTypeFactory
from world.societies.factories import OrganizationMembershipFactory


def _bind_account_to_sheet(account, sheet):
    """Give *account* an active tenure over *sheet* — mirrors item-inventory tests."""
    player_data = PlayerDataFactory(account=account)
    roster_entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry, end_date=None)


class ShipViewSetTests(TestCase):
    """GET /api/ships/ships/ — owner-scoped list + retrieve."""

    def setUp(self) -> None:
        self.owner_account = AccountFactory(username="ship_owner")
        self.owner_sheet = CharacterSheetFactory()
        _bind_account_to_sheet(self.owner_account, self.owner_sheet)
        self.owner_persona = self.owner_sheet.primary_persona

        self.other_account = AccountFactory(username="ship_other")
        self.other_sheet = CharacterSheetFactory()
        _bind_account_to_sheet(self.other_account, self.other_sheet)
        self.other_persona = self.other_sheet.primary_persona

        self.ship_type = ShipTypeFactory(name="Sloop-ViewSetTest")
        self.owned_ship = ShipDetailsFactory(ship_type=self.ship_type)
        self.owned_ship.building.owner_persona = self.owner_persona
        self.owned_ship.building.save(update_fields=["owner_persona"])

        # A ship the owner has no standing over at all.
        self.unowned_ship = ShipDetailsFactory(ship_type=self.ship_type)

        self.client = APIClient()
        self.client.force_authenticate(user=self.owner_account)

    def test_list_unauthenticated_returns_403(self) -> None:
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/ships/ships/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_sees_their_ship_in_list(self) -> None:
        response = self.client.get("/api/ships/ships/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.owned_ship.pk, result_ids)

    def test_list_excludes_ships_owner_does_not_hold(self) -> None:
        response = self.client.get("/api/ships/ships/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(self.unowned_ship.pk, result_ids)

    def test_non_owner_does_not_see_ship_in_list(self) -> None:
        self.client.force_authenticate(user=self.other_account)

        response = self.client.get("/api/ships/ships/")

        result_ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(self.owned_ship.pk, result_ids)

    def test_non_owner_retrieve_returns_404(self) -> None:
        """Queryset scoping means a non-owner's detail lookup 404s (never leaks existence)."""
        self.client.force_authenticate(user=self.other_account)

        response = self.client.get(f"/api/ships/ships/{self.owned_ship.pk}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_retrieve_returns_effective_stats(self) -> None:
        response = self.client.get(f"/api/ships/ships/{self.owned_ship.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["effective_handling"], self.owned_ship.effective_handling())
        self.assertEqual(response.data["effective_armament"], self.owned_ship.effective_armament())
        self.assertEqual(response.data["effective_hull"], self.owned_ship.effective_hull())
        self.assertFalse(response.data["needs_repair"])
        self.assertEqual(response.data["ship_type"]["name"], self.ship_type.name)
        self.assertEqual(response.data["owner_persona_id"], self.owner_persona.pk)

    def test_covenant_member_sees_covenant_owned_ship(self) -> None:
        """Ownership via a covenant deed-holder (Area ownership) is honored too."""
        covenant = CovenantFactory()
        OrganizationMembershipFactory(
            organization=covenant.organization, persona=self.other_persona
        )
        covenant_ship = ShipDetailsFactory(ship_type=self.ship_type)
        transfer_ownership(area=covenant_ship.building.area, to_organization=covenant.organization)

        self.client.force_authenticate(user=self.other_account)
        response = self.client.get("/api/ships/ships/")

        result_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(covenant_ship.pk, result_ids)
        self.assertEqual(response.data["results"][0].get("owner_covenant_name") is not None, True)

    def test_pagination_present(self) -> None:
        response = self.client.get("/api/ships/ships/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)

    def test_filter_by_needs_repair(self) -> None:
        self.owned_ship.needs_repair = True
        self.owned_ship.save(update_fields=["needs_repair"])

        response = self.client.get("/api/ships/ships/?needs_repair=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(result_ids, {self.owned_ship.pk})


class ShipTypeViewSetTests(TestCase):
    """GET /api/ships/ship-types/ — read-only catalog."""

    def setUp(self) -> None:
        self.account = AccountFactory(username="ship_type_reader")
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_list_unauthenticated_returns_403(self) -> None:
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/ships/ship-types/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_returns_catalog(self) -> None:
        ship_type = ShipTypeFactory(name="Brigantine-ViewSetTest")

        response = self.client.get("/api/ships/ship-types/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row["name"] for row in response.data}
        self.assertIn(ship_type.name, names)

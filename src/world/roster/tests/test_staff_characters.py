"""Staff OOC character mint (#3283) — service + endpoint."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.roster.models import RosterEntry, RosterTenure
from world.roster.services.staff_characters import StaffMintError, mint_staff_character


class MintStaffCharacterServiceTests(TestCase):
    def test_mint_creates_full_working_set(self) -> None:
        account = AccountFactory(username="staffer", is_staff=True)
        character = mint_staff_character(account, "Apostate Builder")
        assert character.db_key == "Apostate Builder"
        sheet = character.sheet_data
        entry = RosterEntry.objects.get(character_sheet=sheet)
        assert entry.roster.name == "NPC"
        tenure = RosterTenure.objects.get(roster_entry=entry)
        assert tenure.player_data.account_id == account.pk
        assert tenure.approved_date is not None

    def test_duplicate_name_refused(self) -> None:
        account = AccountFactory(username="staffer2", is_staff=True)
        mint_staff_character(account, "Twin Name")
        with self.assertRaises(StaffMintError) as caught:
            mint_staff_character(account, "twin name")
        assert "already exists" in caught.exception.user_message

    def test_blank_name_refused(self) -> None:
        account = AccountFactory(username="staffer3", is_staff=True)
        with self.assertRaises(StaffMintError):
            mint_staff_character(account, "   ")


class MintBuilderCharacterEndpointTests(APITestCase):
    def test_staff_mints_via_endpoint(self) -> None:
        account = AccountFactory(username="endpoint_staff", is_staff=True)
        self.client.force_authenticate(user=account)
        response = self.client.post(
            "/api/world-builder/areas/mint-builder-character/",
            {"name": "Endpoint Builder"},
            format="json",
        )
        assert response.status_code == 201, response.content
        assert response.data["name"] == "Endpoint Builder"
        entry = RosterEntry.objects.get(character_sheet_id=response.data["character_id"])
        assert entry.roster.name == "NPC"

    def test_non_staff_rejected(self) -> None:
        account = AccountFactory(username="endpoint_player", is_staff=False)
        self.client.force_authenticate(user=account)
        response = self.client.post(
            "/api/world-builder/areas/mint-builder-character/",
            {"name": "Sneaky Builder"},
            format="json",
        )
        assert response.status_code in (403, 404)
        assert not RosterEntry.objects.filter(
            character_sheet__character__db_key="Sneaky Builder"
        ).exists()

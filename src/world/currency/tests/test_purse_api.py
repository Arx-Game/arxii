"""Tests for the self-scoped personal purse read endpoint (#1446 bundle 2)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)

PURSE_URL = "/api/currency/purse/{pk}/"


def _played_sheet(*, account):
    """Create a character sheet with an active tenure held by ``account``."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    RosterEntryFactory(character_sheet=sheet, roster=RosterFactory())
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=sheet.roster_entry)
    return sheet


class PurseApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        self.sheet = _played_sheet(account=self.account)

    def test_owner_reads_balance(self) -> None:
        purse = get_or_create_purse(self.sheet)
        purse.balance = 1347
        purse.save(update_fields=["balance"])

        response = self.client.get(PURSE_URL.format(pk=self.sheet.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["balance"], 1347)

    def test_purseless_character_reads_zero(self) -> None:
        response = self.client.get(PURSE_URL.format(pk=self.sheet.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["balance"], 0)

    def test_stranger_is_404(self) -> None:
        stranger_sheet = _played_sheet(account=AccountFactory())

        response = self.client.get(PURSE_URL.format(pk=stranger_sheet.pk))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_is_denied(self) -> None:
        self.client.force_authenticate(user=None)

        response = self.client.get(PURSE_URL.format(pk=self.sheet.pk))

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

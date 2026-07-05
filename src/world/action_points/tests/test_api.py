"""Tests for the self-scoped action-points read endpoint (#1446 bundle 2)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.action_points.factories import ActionPointPoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)

AP_URL = "/api/action-points/{pk}/"


def _played_character(*, account):
    """Create a character (with sheet + active tenure held by ``account``)."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    RosterEntryFactory(character_sheet=sheet, roster=RosterFactory())
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=sheet.roster_entry)
    return character


class ActionPointsApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        self.character = _played_character(account=self.account)

    def test_owner_reads_pool(self) -> None:
        pool = ActionPointPoolFactory(character=self.character, current=140, banked=25)

        response = self.client.get(AP_URL.format(pk=self.character.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current"], 140)
        self.assertEqual(response.data["banked"], 25)
        self.assertEqual(response.data["effective_maximum"], pool.get_effective_maximum())

    def test_poolless_character_reads_defaults(self) -> None:
        response = self.client.get(AP_URL.format(pk=self.character.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["current"], 0)
        self.assertGreaterEqual(response.data["effective_maximum"], 1)

    def test_stranger_is_404(self) -> None:
        stranger_character = _played_character(account=AccountFactory())

        response = self.client.get(AP_URL.format(pk=stranger_character.pk))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_get_on_non_character_pk_is_404_and_creates_no_pool(self) -> None:
        from evennia_extensions.factories import ObjectDBFactory
        from world.action_points.models import ActionPointPool

        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        vase = ObjectDBFactory(db_key="a vase of flowers")

        response = self.client.get(AP_URL.format(pk=vase.pk))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(ActionPointPool.objects.filter(character=vase).exists())

    def test_anonymous_is_denied(self) -> None:
        self.client.force_authenticate(user=None)

        response = self.client.get(AP_URL.format(pk=self.character.pk))

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

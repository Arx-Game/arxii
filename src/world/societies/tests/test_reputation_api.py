"""DRF tests for the societies organization-reputation API (#1446)."""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.societies.factories import (
    OrganizationFactory,
    OrganizationReputationFactory,
)


def _active_primary_persona(*, account):
    """Create a character sheet + active tenure and return its primary persona."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    roster = RosterFactory()
    RosterEntryFactory(character_sheet=sheet, roster=roster)
    player_data = PlayerData.objects.create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=sheet.roster_entry)
    return sheet.primary_persona


class OrganizationReputationApiTests(TestCase):
    """Tests for the /api/societies/reputations/ endpoint."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        self.persona = _active_primary_persona(account=self.account)
        self.organization = OrganizationFactory(name="Standing Org")
        self.reputation = OrganizationReputationFactory(
            persona=self.persona,
            organization=self.organization,
            value=350,
        )

    def test_lists_own_reputations_only(self) -> None:
        """Users see their own persona's org reputations with named tiers, nothing else."""
        other_account = AccountFactory()
        other_persona = _active_primary_persona(account=other_account)
        OrganizationReputationFactory(persona=other_persona, value=-400)

        response = self.client.get(reverse("societies:organization-reputation-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], self.organization.id)
        self.assertEqual(rows[0]["organization_name"], self.organization.name)
        self.assertEqual(rows[0]["persona"], self.persona.pk)  # client filters by viewed persona
        self.assertEqual(rows[0]["tier"], "liked")
        self.assertNotIn("value", rows[0])

    def test_filter_by_organization(self) -> None:
        other_org = OrganizationFactory(name="Other Org")
        OrganizationReputationFactory(persona=self.persona, organization=other_org, value=100)

        response = self.client.get(
            reverse("societies:organization-reputation-list"),
            {"organization": self.organization.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], self.organization.id)

    def test_unauthenticated_requests_are_rejected(self) -> None:
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse("societies:organization-reputation-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

"""Estate API scoping, freeze, and leak containment (#1985)."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.estates.constants import BequestKind
from world.estates.factories import (
    EstateClaimFactory,
    WillExecutorFactory,
    WillFactory,
)
from world.estates.services import open_settlement
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _player_with_sheet():
    account = AccountFactory()
    sheet = CharacterSheetFactory()
    RosterTenureFactory(
        roster_entry=RosterEntryFactory(character_sheet=sheet),
        player_data__account=account,
        end_date=None,
    )
    return account, sheet


class WillApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.account, self.sheet = _player_with_sheet()
        self.other_account, self.other_sheet = _player_with_sheet()
        self.client.force_authenticate(self.account)

    def test_create_and_read_own_will(self):
        response = self.client.post(
            "/api/estates/wills/",
            {"character_sheet": self.sheet.pk, "testament_text": "All to the crows."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        listing = self.client.get("/api/estates/wills/")
        self.assertEqual(listing.json()["count"], 1)

    def test_foreign_will_is_invisible(self):
        will = WillFactory(character_sheet=self.other_sheet)
        response = self.client.get(f"/api/estates/wills/{will.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_frozen_will_refuses_edits(self):
        will = WillFactory(character_sheet=self.sheet)
        open_settlement(self.sheet)
        response = self.client.patch(
            f"/api/estates/wills/{will.pk}/", {"testament_text": "Changed my mind."}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("sealed", str(response.json()))

    def test_bequest_validation_persona_only_kinds(self):
        from world.societies.factories import OrganizationFactory

        will = WillFactory(character_sheet=self.sheet)
        response = self.client.post(
            "/api/estates/bequests/",
            {
                "will": will.pk,
                "kind": BequestKind.BUSINESS,
                "recipient_organization": OrganizationFactory().pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class SettlementApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.executor_account, self.executor_sheet = _player_with_sheet()
        self.stranger_account, _ = _player_with_sheet()
        self.deceased_sheet = CharacterSheetFactory()
        will = WillFactory(character_sheet=self.deceased_sheet)
        WillExecutorFactory(will=will, persona=self.executor_sheet.primary_persona)
        self.settlement = open_settlement(self.deceased_sheet)

    def test_executor_sees_settlement(self):
        self.client.force_authenticate(self.executor_account)
        response = self.client.get(f"/api/estates/settlements/{self.settlement.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")

    def test_stranger_gets_404(self):
        self.client.force_authenticate(self.stranger_account)
        response = self.client.get(f"/api/estates/settlements/{self.settlement.pk}/")
        self.assertEqual(response.status_code, 404)


class ClaimApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.claimant_account, self.claimant_sheet = _player_with_sheet()
        self.other_account, _ = _player_with_sheet()
        self.claim = EstateClaimFactory(claimant_persona=self.claimant_sheet.primary_persona)

    def test_claimant_sees_claim(self):
        self.client.force_authenticate(self.claimant_account)
        response = self.client.get(f"/api/estates/claims/{self.claim.pk}/")
        self.assertEqual(response.status_code, 200)

    def test_non_claimant_gets_404(self):
        self.client.force_authenticate(self.other_account)
        response = self.client.get(f"/api/estates/claims/{self.claim.pk}/")
        self.assertEqual(response.status_code, 404)

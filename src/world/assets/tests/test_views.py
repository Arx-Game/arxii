"""API tests for the read-only NPCAsset endpoint (#1872)."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase
from rest_framework.test import APIClient

from world.assets.factories import NPCAssetFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class NPCAssetViewSetTests(EvenniaTestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.entry = RosterEntryFactory(character_sheet=self.sheet)
        # RosterEntryFactory doesn't auto-create a tenure — first_tenure needs
        # an explicit player_number=1 RosterTenure to resolve.
        self.tenure = RosterTenureFactory(roster_entry=self.entry, player_number=1)
        self.account = self.tenure.player_data.account
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_list_scoped_to_own_persona(self) -> None:
        mine = NPCAssetFactory(promoter_persona=self.sheet.primary_persona)
        NPCAssetFactory()  # someone else's — must not appear
        response = self.client.get("/api/assets/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [mine.pk])

    def test_unauthenticated_rejected(self) -> None:
        # DRF returns 403, not 401, here: SessionAuthentication is the only
        # authenticator configured (REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES)
        # and its authenticate_header() returns None, so there's no
        # WWW-Authenticate challenge to trigger a 401 — matches
        # world.companions.tests.test_views's identical test_unauthenticated_is_denied.
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/assets/")
        self.assertEqual(response.status_code, 403)

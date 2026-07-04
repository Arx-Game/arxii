"""Tests for the companions read-only API (#672)."""

from __future__ import annotations

from rest_framework.test import APITestCase

from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.roster.factories import RosterTenureFactory


class CompanionViewSetTests(APITestCase):
    def test_lists_only_own_active_companions(self) -> None:
        tenure = RosterTenureFactory()
        account = tenure.player_data.account
        sheet = tenure.roster_entry.character_sheet
        mine = CompanionFactory(owner=sheet)
        CompanionFactory()  # someone else's — must not appear

        self.client.force_authenticate(account)
        response = self.client.get("/api/companions/companions/")

        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data["results"]]
        self.assertIn(mine.name, names)
        self.assertEqual(len(names), 1)

    def test_unauthenticated_is_denied(self) -> None:
        # DRF returns 403, not 401, here: SessionAuthentication is the only
        # authenticator configured (REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES)
        # and its authenticate_header() returns None, so there's no
        # WWW-Authenticate challenge to trigger a 401 — matches
        # world.ships.tests.test_views's identical
        # test_list_unauthenticated_returns_403.
        response = self.client.get("/api/companions/companions/")

        self.assertEqual(response.status_code, 403)


class CompanionArchetypeViewSetTests(APITestCase):
    def test_lists_catalog(self) -> None:
        tenure = RosterTenureFactory()
        archetype = CompanionArchetypeFactory()

        self.client.force_authenticate(tenure.player_data.account)
        response = self.client.get("/api/companions/companion-archetypes/")

        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data]
        self.assertIn(archetype.name, names)

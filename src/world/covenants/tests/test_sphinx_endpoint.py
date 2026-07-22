"""Tests for GET /api/covenants/roles/sphinx/ — the Sphinx of Black Quartz (#2640).

Self-character only, read-only. Mirrors the tenure-chain auth setup in
``test_covenant_powers_endpoint.py``.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class SphinxEndpointTestCase(TestCase):
    """Base: an authenticated user with an active tenure on a character sheet."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CovenantRoleFactory,
            CovenantRoleTechniqueSpecialtyFactory,
        )
        from world.magic.constants import TechniqueFunction
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        cls.user = AccountDB.objects.create_user(
            username="sphinx_user",
            email="sphinx@test.com",
            password="testpass123",
        )
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.tenure = RosterTenureFactory(
            roster_entry=cls.roster_entry,
            player_data=cls.player_data,
            end_date=None,
        )

        cls.role = CovenantRoleFactory(name="Sphinx Test Vow")
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=cls.role, function=TechniqueFunction.WEAKEN
        )
        technique = TechniqueFactory()
        CharacterTechniqueFactory(character=cls.sheet, technique=technique)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _url(self, role_id: int) -> str:
        return f"/api/covenants/roles/sphinx/?role={role_id}"


class SphinxEndpointShapeTests(SphinxEndpointTestCase):
    def test_returns_verdict_shape(self) -> None:
        response = self.client.get(self._url(self.role.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("tier", response.data)
        self.assertIn("role_name", response.data)
        self.assertIn("demands", response.data)
        self.assertIn("shopping_list", response.data)
        self.assertEqual(response.data["role_name"], self.role.name)

    def test_role_lookup_by_slug(self) -> None:
        response = self.client.get(f"/api/covenants/roles/sphinx/?role={self.role.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role_name"], self.role.name)

    def test_missing_role_param_is_400(self) -> None:
        response = self.client.get("/api/covenants/roles/sphinx/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_role_is_404(self) -> None:
        response = self.client.get("/api/covenants/roles/sphinx/?role=999999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SphinxEndpointAuthTests(SphinxEndpointTestCase):
    def test_unauthenticated_denied(self) -> None:
        unauthenticated = APIClient()
        response = unauthenticated.get(self._url(self.role.pk))
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_no_active_character_is_400(self) -> None:
        from evennia.accounts.models import AccountDB

        no_char_user = AccountDB.objects.create_user(
            username="sphinx_no_char",
            email="sphinx_no_char@test.com",
            password="testpass123",
        )
        client = APIClient()
        client.force_authenticate(user=no_char_user)
        response = client.get(self._url(self.role.pk))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

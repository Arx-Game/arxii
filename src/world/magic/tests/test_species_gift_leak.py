"""Regression test: species Minor Gift concealment / leak gate (ADR-0033, #1580).

A species Minor Gift (GiftKind.MINOR, e.g. vampirism) can out a concealed
identity if it leaks through the CharacterGiftViewSet to a different viewer
account.  This test proves that CharacterGiftViewSet is account-scoped — a
viewer authenticated as a different account does NOT receive the target
character's gifts in the list response.

Broad gift-visibility hardening (staff reads, public catalog, per-gift
concealment toggles) is owned by #1587; this test only asserts the #1580
invariant: no new public read of species gifts was introduced.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind
from world.magic.factories import CharacterGiftFactory, GiftFactory
from world.roster.factories import RosterTenureFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure."""
    character.account = account
    account.characters.add(character)
    return RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
    )


class SpeciesGiftLeakGateTests(APITestCase):
    """CharacterGiftViewSet must not expose another account's species Minor Gift."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Target: character who holds a species Minor Gift.
        cls.target_account = AccountFactory(username="species_gift_target")
        cls.target_character = CharacterFactory(db_key="SpeciesTarget")
        cls.target_sheet = CharacterSheetFactory(character=cls.target_character)
        _link_account_to_sheet(cls.target_account, cls.target_character, cls.target_sheet)

        cls.species_gift = GiftFactory(
            name="Vampiric Nature",
            kind=GiftKind.MINOR,
        )
        cls.target_cg = CharacterGiftFactory(
            character=cls.target_sheet,
            gift=cls.species_gift,
        )

        # Viewer: a different account with their own character.
        cls.viewer_account = AccountFactory(username="species_gift_viewer")
        cls.viewer_character = CharacterFactory(db_key="SpeciesViewer")
        cls.viewer_sheet = CharacterSheetFactory(character=cls.viewer_character)
        _link_account_to_sheet(cls.viewer_account, cls.viewer_character, cls.viewer_sheet)

        cls.viewer_gift = GiftFactory(name="Viewer Own Gift", kind=GiftKind.MAJOR)
        cls.viewer_cg = CharacterGiftFactory(
            character=cls.viewer_sheet,
            gift=cls.viewer_gift,
        )

    # ------------------------------------------------------------------
    # Core leak gate
    # ------------------------------------------------------------------

    @staticmethod
    def _gift_ids(response) -> set[int]:
        """Extract CharacterGift PKs from a list response.

        CharacterGiftViewSet has no pagination class, so response.data is a
        plain list (not {"results": [...]}). Centralise the extraction so a
        future pagination change only needs one fix here.
        """
        data = response.data
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        return {row["id"] for row in rows}

    def test_viewer_cannot_list_target_species_gift(self) -> None:
        """A different account's character-gift list must not include the target's gift."""
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(reverse("magic:character-gift-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = self._gift_ids(response)
        self.assertNotIn(
            self.target_cg.pk,
            returned_ids,
            "Species Minor Gift of another character must not appear in the viewer's list.",
        )

    def test_viewer_cannot_retrieve_target_species_gift_detail(self) -> None:
        """Direct retrieve of another account's CharacterGift must return 404."""
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(reverse("magic:character-gift-detail", args=[self.target_cg.pk]))
        # Queryset filter strips foreign rows → 404, not 403.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_viewer_sees_only_own_gift(self) -> None:
        """The viewer's own gift is present and the target's gift is absent."""
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(reverse("magic:character-gift-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = self._gift_ids(response)
        self.assertIn(
            self.viewer_cg.pk,
            returned_ids,
            "Viewer's own gift must appear in their list.",
        )
        self.assertNotIn(
            self.target_cg.pk,
            returned_ids,
            "Target's species gift must not appear in the viewer's list.",
        )

    def test_unauthenticated_request_is_rejected(self) -> None:
        """Unauthenticated requests must be rejected (401 or 403)."""
        response = self.client.get(reverse("magic:character-gift-list"))
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_target_can_see_own_species_gift(self) -> None:
        """Sanity check: the target account can list its own species Minor Gift."""
        self.client.force_authenticate(user=self.target_account)
        response = self.client.get(reverse("magic:character-gift-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = self._gift_ids(response)
        self.assertIn(
            self.target_cg.pk,
            returned_ids,
            "Target must be able to see their own species gift.",
        )

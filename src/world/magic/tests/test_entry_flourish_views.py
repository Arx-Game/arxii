"""API tests for the entry-flourish offer REST surface (#1140): pending inbox + respond.

Covers:
    1. List scoped to the authenticated account's own offers
    2. Detail retrieval of a foreign account's offer is a 404 (queryset-scoped)
    3. Respond happy path — 200 with result, offer row deleted, grant written
    4. Respond rejects a non-owned offer (400, row survives)
    5. Respond rejects an unclaimed resonance_id (400)
    6. Unauthenticated requests rejected (401/403)
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.roster.factories import RosterTenureFactory

_PENDING_URL = "/api/magic/entry-flourish/pending/"
_RESPOND_URL = "/api/magic/entry-flourish/respond/"


def _make_tenure_with_offer(scene=None):
    """Return (tenure, offer, character_resonance) for a fresh authenticated user.

    Creates a RosterTenure (with linked account via the factory), seeds a
    CharacterResonance so the character has a claimed resonance to broadcast,
    and creates the pending offer row.
    """
    tenure = RosterTenureFactory()
    sheet = tenure.roster_entry.character_sheet
    char_resonance = CharacterResonanceFactory(character_sheet=sheet)
    offer = PendingEntryFlourishOffer.objects.create(
        character_sheet=sheet,
        scene=scene,
    )
    return tenure, offer, char_resonance


class PendingEntryFlourishOfferListTests(APITestCase):
    """GET /api/magic/entry-flourish/pending/ — account-scoped inbox."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.my_tenure, cls.my_offer, cls.my_char_resonance = _make_tenure_with_offer()
        cls.other_tenure, cls.other_offer, cls.other_char_resonance = _make_tenure_with_offer()
        cls.my_account = cls.my_tenure.player_data.account

    def test_list_scoped_to_own_offers(self) -> None:
        """My offer appears in the list; another account's offer does not."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        self.assertEqual(response.status_code, 200, response.content)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.my_offer.pk, result_ids)
        self.assertNotIn(self.other_offer.pk, result_ids)

    def test_list_returns_expected_fields(self) -> None:
        """Each row includes id, character_sheet_id, scene_id, created_at."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        self.assertEqual(response.status_code, 200, response.content)
        rows = [row for row in response.data["results"] if row["id"] == self.my_offer.pk]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("id", row)
        self.assertIn("character_sheet_id", row)
        self.assertIn("scene_id", row)
        self.assertIn("created_at", row)

    def test_retrieve_foreign_offer_404(self) -> None:
        """Detail retrieval of another account's offer is a 404 (queryset-scoped)."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(f"{_PENDING_URL}{self.other_offer.pk}/")
        self.assertEqual(response.status_code, 404, response.content)

    def test_list_unauthenticated_rejected(self) -> None:
        """Unauthenticated GET returns 401 or 403."""
        response = self.client.get(_PENDING_URL)
        self.assertIn(response.status_code, (401, 403))


class EntryFlourishRespondViewTests(APITestCase):
    """POST /api/magic/entry-flourish/respond/ — pick a resonance to broadcast."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.my_tenure, cls.my_offer, cls.my_char_resonance = _make_tenure_with_offer()
        cls.other_tenure, cls.other_offer, cls.other_char_resonance = _make_tenure_with_offer()
        cls.my_account = cls.my_tenure.player_data.account

    def test_respond_happy_path_returns_result(self) -> None:
        """POSTing a claimed resonance_id returns 200 with result + deletes offer."""
        # Each test needs a fresh offer (respond deletes it).
        tenure, offer, char_resonance = _make_tenure_with_offer()
        account = tenure.player_data.account
        self.client.force_authenticate(user=account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": offer.pk, "resonance_id": char_resonance.resonance_id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        self.assertIn("resonance_id", data)
        self.assertIn("resonance_name", data)
        self.assertIn("granted_amount", data)
        self.assertIn("scene_id", data)
        self.assertEqual(data["resonance_id"], char_resonance.resonance_id)
        # Offer row must be deleted
        self.assertFalse(PendingEntryFlourishOffer.objects.filter(pk=offer.pk).exists())

    def test_respond_fires_grant(self) -> None:
        """Happy-path respond creates an EntryFlourishRecord grant row."""
        from world.magic.models import EntryFlourishRecord

        tenure, offer, char_resonance = _make_tenure_with_offer()
        account = tenure.player_data.account
        sheet = tenure.roster_entry.character_sheet
        self.client.force_authenticate(user=account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": offer.pk, "resonance_id": char_resonance.resonance_id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(EntryFlourishRecord.objects.filter(character_sheet=sheet).exists())

    def test_respond_rejects_non_owned_offer(self) -> None:
        """An offer belonging to another account returns 404; the row survives."""
        # Re-create other_offer each time (other tests may delete it)
        _, other_offer, _ = _make_tenure_with_offer()
        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": other_offer.pk, "resonance_id": self.my_char_resonance.resonance_id},
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.assertTrue(PendingEntryFlourishOffer.objects.filter(pk=other_offer.pk).exists())

    def test_respond_rejects_unclaimed_resonance(self) -> None:
        """A resonance_id not claimed by the sheet raises 400."""
        tenure, offer, _ = _make_tenure_with_offer()
        unclaimed = ResonanceFactory()
        account = tenure.player_data.account
        self.client.force_authenticate(user=account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": offer.pk, "resonance_id": unclaimed.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_respond_nonexistent_offer_returns_404(self) -> None:
        """A non-existent offer_id returns 404."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": 999999, "resonance_id": self.my_char_resonance.resonance_id},
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.content)

    def test_respond_unauthenticated_rejected(self) -> None:
        """Unauthenticated POST returns 401 or 403."""
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": 1, "resonance_id": 1},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))

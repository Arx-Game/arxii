"""Endpoint test for POST /api/character-creation/drafts/<pk>/add-to-roster/ (#2971).

``CharacterDraftViewSet.add_to_roster`` catches ``CharacterCreationError`` and maps it
to a 400; as of the #2971 final-review fix it also catches ``GiftResonanceUnresolvable``
(``world.magic.exceptions``) the same way — a gift grant during finalize that can't
resolve any resonance for its latent GIFT thread must not surface as an unhandled 500.
"""

from __future__ import annotations

from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.magic.exceptions import GiftResonanceUnresolvable


class AddToRosterViewGiftResonanceUnresolvableTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)

    def _url(self, draft) -> str:
        return f"/api/character-creation/drafts/{draft.pk}/add-to-roster/"

    def test_unresolvable_gift_resonance_maps_to_400_not_500(self) -> None:
        draft = CharacterDraftFactory(account=self.staff)
        self.client.force_authenticate(user=self.staff)

        with patch(
            "world.character_creation.views.finalize_character",
            side_effect=GiftResonanceUnresolvable,
        ):
            response = self.client.post(self._url(draft), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertEqual(response.data["detail"], "Character creation failed.")

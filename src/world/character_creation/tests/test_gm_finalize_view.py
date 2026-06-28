"""Endpoint tests for the GM character-finalize flow (#1506).

POST /api/character-creation/drafts/<pk>/finalize-gm/ — a player-GM finalizes a draft
onto the Available roster for a table they own, stamped with GM_TABLE provenance.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.test import APITestCase

from world.character_creation.factories import CharacterDraftFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.roster.models import RosterEntry
from world.roster.models.choices import CreationProvenance


class GMFinalizeViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.gm)

    def _url(self, draft) -> str:
        return f"/api/character-creation/drafts/{draft.pk}/finalize-gm/"

    def _draft(self, account=None):
        return CharacterDraftFactory(
            account=account or self.gm.account,
            draft_data={"first_name": "Aurelius"},
        )

    def test_owner_finalizes_with_gm_table_provenance(self) -> None:
        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": self.table.pk, "story_title": "The Grand Design"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        entry = RosterEntry.objects.get(pk=response.data["roster_entry_id"])
        self.assertEqual(entry.creation_provenance, CreationProvenance.GM_TABLE)
        self.assertEqual(entry.created_for_table, self.table)
        self.assertEqual(entry.created_by_account, self.gm.account)
        self.assertEqual(entry.roster.name, "Available")

    def test_non_owner_of_the_table_is_forbidden(self) -> None:
        other_gm = GMProfileFactory()
        draft = self._draft(account=other_gm.account)
        self.client.force_authenticate(user=other_gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": self.table.pk, "story_title": "Not Mine"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_story_title_returns_400(self) -> None:
        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": self.table.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_table_returns_404(self) -> None:
        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": 999999, "story_title": "Ghost Table"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

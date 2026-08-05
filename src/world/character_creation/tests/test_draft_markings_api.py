"""API tests for the CG draft-markings CRUD (#2985).

Rows scope to the requester's own draft; ``draft`` is never client-supplied.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.models import DraftMarking

URL = "/api/character-creation/draft-markings/"


class DraftMarkingAPITests(TestCase):
    def setUp(self) -> None:
        self.draft = CharacterDraftFactory()
        self.account = self.draft.account
        self.other_account = AccountFactory(username="marking_other")
        self.client = APIClient()

    def test_create_binds_to_own_draft(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            URL,
            {
                "body_region": "torso",
                "kind": "tattoo",
                "name": "a coiled serpent tattoo",
                "description": "Ink winding around the ribs.",
            },
            format="json",
        )
        assert response.status_code == 201, response.content
        marking = DraftMarking.objects.get(pk=response.json()["id"])
        assert marking.draft_id == self.draft.pk

    def test_create_without_draft_fails(self):
        self.client.force_authenticate(user=self.other_account)
        response = self.client.post(
            URL,
            {"body_region": "torso", "kind": "tattoo", "name": "no draft ink"},
            format="json",
        )
        assert response.status_code == 400

    def test_list_scopes_to_own_draft(self):
        DraftMarking.objects.create(
            draft=self.draft, body_region="face", kind="scar", name="a duelist's scar"
        )
        other_draft = CharacterDraftFactory(account=self.other_account)
        DraftMarking.objects.create(
            draft=other_draft, body_region="back", kind="brand", name="another's brand"
        )
        self.client.force_authenticate(user=self.account)
        names = [row["name"] for row in self.client.get(URL).json()]
        assert names == ["a duelist's scar"]

    def test_delete_own_marking(self):
        marking = DraftMarking.objects.create(
            draft=self.draft, body_region="face", kind="scar", name="a duelist's scar"
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.delete(f"{URL}{marking.pk}/")
        assert response.status_code == 204
        assert not DraftMarking.objects.filter(pk=marking.pk).exists()

    def test_cannot_delete_foreign_marking(self):
        other_draft = CharacterDraftFactory(account=self.other_account)
        marking = DraftMarking.objects.create(
            draft=other_draft, body_region="back", kind="brand", name="another's brand"
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.delete(f"{URL}{marking.pk}/")
        assert response.status_code == 404
        assert DraftMarking.objects.filter(pk=marking.pk).exists()

    def test_invalid_kind_rejected(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            URL,
            {"body_region": "torso", "kind": "ritual_mark", "name": "old vocabulary"},
            format="json",
        )
        assert response.status_code == 400

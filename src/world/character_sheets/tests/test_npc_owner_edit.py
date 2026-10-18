"""The GM who owns a story NPC edits its sheet; nothing else widens (#4418)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.roster.constants import NPCLoanStatus
from world.roster.factories import NPCLoanFactory
from world.roster.services.staff_characters import mint_story_npc


class NPCOwnerEditTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()
        cls.owner = AccountFactory(username="npc_owner_gm")
        GMProfileFactory(account=cls.owner, level=GMLevel.JUNIOR)
        cls.other_gm = AccountFactory(username="npc_other_gm")
        GMProfileFactory(account=cls.other_gm, level=GMLevel.JUNIOR)
        cls.borrower = AccountFactory(username="npc_borrower")
        cls.sheet = mint_story_npc(gm_account=cls.owner, name="Captain Orlo").sheet_data
        NPCLoanFactory(
            roster_entry=cls.sheet.roster_entry,
            borrower=cls.borrower,
            offered_by=cls.owner,
            status=NPCLoanStatus.ACTIVE,
        )
        cls.edit_url = f"/api/character-sheets/{cls.sheet.pk}/staff-edit/"
        cls.claim_url = f"/api/character-sheets/{cls.sheet.pk}/staff-house-claim/"

    def setUp(self) -> None:
        self.client = APIClient()

    def _patch(self, account):
        self.client.force_authenticate(user=account)
        return self.client.patch(
            self.edit_url,
            {"vocation": "Soldier", "concept": "A loyal officer"},
            format="json",
        )

    def test_owner_edits_identity_and_prose(self) -> None:
        response = self._patch(self.owner)
        assert response.status_code == 200, response.data
        profile = self.sheet.true_profile
        profile.refresh_from_db()
        assert profile.concept == "A loyal officer"

    def test_owner_cannot_claim_a_house(self) -> None:
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(self.claim_url, {}, format="json")
        assert response.status_code == 404

    def test_borrower_cannot_edit(self) -> None:
        assert self._patch(self.borrower).status_code == 404

    def test_other_gm_cannot_edit(self) -> None:
        assert self._patch(self.other_gm).status_code == 404

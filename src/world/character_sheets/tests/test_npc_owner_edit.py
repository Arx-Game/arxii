"""The GM who owns a story NPC edits its sheet; nothing else widens (#4418)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.roster.constants import NPCLoanStatus
from world.roster.factories import NPCLoanFactory, RosterEntryFactory
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
        self.sheet.refresh_from_db()
        assert self.sheet.vocation == "Soldier"

    def test_owner_cannot_claim_a_house(self) -> None:
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(self.claim_url, {}, format="json")
        assert response.status_code == 404

    def test_borrower_cannot_edit(self) -> None:
        assert self._patch(self.borrower).status_code == 404

    def test_other_gm_cannot_edit(self) -> None:
        assert self._patch(self.other_gm).status_code == 404

    def test_every_gated_action_opens_for_the_owner_and_not_for_another_gm(self) -> None:
        base = f"/api/character-sheets/{self.sheet.pk}"
        actions = [
            ("patch", "staff-stats", {"stats": {}}),
            ("patch", "staff-skills", {}),
            ("patch", "staff-path", {"level": 2}),
            ("post", "staff-magic", {}),
            ("get", "staff-magic-options", None),
            ("get", "staff-options", None),
        ]
        for method, path, payload in actions:
            kwargs = {} if payload is None else {"data": payload, "format": "json"}
            with self.subTest(path=path):
                self.client.force_authenticate(user=self.owner)
                owner = getattr(self.client, method)(f"{base}/{path}/", **kwargs)
                assert owner.status_code != 404, owner.content[:300]
                if method == "get":
                    assert owner.status_code == 200
                self.client.force_authenticate(user=self.other_gm)
                other = getattr(self.client, method)(f"{base}/{path}/", **kwargs)
                assert other.status_code == 404

    def test_owning_a_non_npc_character_grants_nothing(self) -> None:
        entry = RosterEntryFactory(created_by_account=self.owner)
        sheet = entry.character_sheet
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            f"/api/character-sheets/{sheet.pk}/staff-edit/", {"vocation": "Soldier"}, format="json"
        )
        assert response.status_code == 404

    def test_staff_edit_payload_reaches_only_the_owner_and_staff(self) -> None:
        detail = f"/api/character-sheets/{self.sheet.pk}/"
        staff = AccountFactory(username="npc_edit_staff", is_staff=True)
        for account, expected in (
            (self.owner, True),
            (staff, True),
            (self.borrower, False),
            (self.other_gm, False),
        ):
            with self.subTest(account=account.username):
                self.client.force_authenticate(user=account)
                response = self.client.get(detail)
                assert response.status_code == 200, response.content[:300]
                assert (response.data["staff_edit"] is not None) is expected

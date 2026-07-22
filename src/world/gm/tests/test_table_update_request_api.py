"""API tests for TableUpdateRequestViewSet (#2631)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import ProfileTextField
from world.distinctions.factories import DistinctionFactory
from world.distinctions.types import DistinctionChangeAction
from world.gm.constants import TableRequestKind, TableRequestStatus
from world.gm.factories import GMTableFactory, GMTableMembershipFactory
from world.gm.services import submit_profile_text_request
from world.scenes.factories import PersonaFactory

BASE = "/api/gm/table-update-requests/"


def _linked_membership(account, table=None):
    """Create an active membership whose persona chains back to ``account``."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    sheet = CharacterSheetFactory(character=char)
    persona = PersonaFactory(character_sheet=sheet)
    if table is None:
        table = GMTableFactory()
    return GMTableMembershipFactory(table=table, persona=persona)


class TableUpdateRequestScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.player = AccountFactory()
        cls.other_player = AccountFactory()
        cls.membership = _linked_membership(cls.player)
        cls.other_membership = _linked_membership(cls.other_player)
        cls.request = submit_profile_text_request(
            cls.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="New text.",
            reasoning="Reason.",
        )
        cls.other_request = submit_profile_text_request(
            cls.other_membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="Other text.",
            reasoning="Reason.",
        )

    def setUp(self):
        self.client = APIClient()

    def test_player_sees_only_own_requests(self):
        self.client.force_authenticate(user=self.player)
        response = self.client.get(BASE)
        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert self.request.pk in ids
        assert self.other_request.pk not in ids

    def test_table_gm_sees_table_requests(self):
        gm_account = self.membership.table.gm.account
        self.client.force_authenticate(user=gm_account)
        response = self.client.get(BASE, {"role": "gm"})
        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert self.request.pk in ids
        assert self.other_request.pk not in ids

    def test_unauthenticated_rejected(self):
        response = self.client.get(BASE)
        assert response.status_code in (401, 403)


class TableUpdateRequestCreateTests(TestCase):
    def setUp(self):
        self.player = AccountFactory()
        self.membership = _linked_membership(self.player)
        self.client = APIClient()
        self.client.force_authenticate(user=self.player)

    def test_create_profile_text_request(self):
        response = self.client.post(
            BASE,
            {
                "membership": self.membership.pk,
                "kind": TableRequestKind.PROFILE_TEXT,
                "field": ProfileTextField.BACKGROUND,
                "proposed_text": "A new story.",
                "reasoning": "The arc happened.",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["status"] == TableRequestStatus.PENDING
        assert response.data["profile_text_details"]["proposed_text"] == "A new story."

    def test_create_distinction_request(self):
        distinction = DistinctionFactory(cost_per_rank=5, max_rank=1)
        response = self.client.post(
            BASE,
            {
                "membership": self.membership.pk,
                "kind": TableRequestKind.DISTINCTION_CHANGE,
                "action": DistinctionChangeAction.ADD,
                "distinction": distinction.pk,
                "reasoning": "Earned in play.",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["distinction_details"]["distinction"] == distinction.pk

    def test_cannot_submit_on_anothers_membership(self):
        stranger_membership = _linked_membership(AccountFactory())
        response = self.client.post(
            BASE,
            {
                "membership": stranger_membership.pk,
                "kind": TableRequestKind.PROFILE_TEXT,
                "field": ProfileTextField.BACKGROUND,
                "proposed_text": "text",
                "reasoning": "reason",
            },
            format="json",
        )
        assert response.status_code == 400


class TableUpdateRequestActionTests(TestCase):
    def setUp(self):
        self.player = AccountFactory()
        self.membership = _linked_membership(self.player)
        self.gm_account = self.membership.table.gm.account
        self.request_obj = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="New text.",
            reasoning="Reason.",
        )
        self.client = APIClient()

    def test_gm_signoff_approve(self):
        self.client.force_authenticate(user=self.gm_account)
        response = self.client.post(
            f"{BASE}{self.request_obj.pk}/signoff/",
            {"approve": True, "notes": "Fits."},
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data["status"] == TableRequestStatus.COMPLETED

    def test_player_cannot_signoff(self):
        self.client.force_authenticate(user=self.player)
        response = self.client.post(
            f"{BASE}{self.request_obj.pk}/signoff/",
            {"approve": True},
            format="json",
        )
        assert response.status_code == 400

    def test_player_withdraw(self):
        self.client.force_authenticate(user=self.player)
        response = self.client.post(f"{BASE}{self.request_obj.pk}/withdraw/")
        assert response.status_code == 200, response.data
        assert response.data["status"] == TableRequestStatus.WITHDRAWN

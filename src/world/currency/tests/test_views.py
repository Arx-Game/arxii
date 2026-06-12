"""Org-books read API (#930 prep)."""

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.scenes.factories import PersonaFactory


class OrgBooksApiTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )

        cls.user = AccountFactory(username="books_user")
        cls.org = OrganizationFactory()
        cls.member = PersonaFactory()
        cls.outsider = PersonaFactory()
        OrganizationMembershipFactory(persona=cls.member, organization=cls.org, rank=3)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _get(self, org_id=None):
        return self.client.get(f"/api/currency/org-books/{org_id or self.org.pk}/")

    def test_member_sees_full_books(self) -> None:
        from world.currency.models import OrgIncomeStream, OrgObligation
        from world.currency.services import (
            extend_loan,
            get_or_create_treasury,
            record_contribution,
            transfer,
        )
        from world.societies.factories import OrganizationFactory

        liege = OrganizationFactory()
        treasury = get_or_create_treasury(self.org)
        transfer(amount=5_000, reason="seed", to_treasury=treasury)
        OrgIncomeStream.objects.create(
            organization=self.org, name="Land taxes", kind="domain_tax", gross_amount=1000
        )
        OrgObligation.objects.create(
            from_organization=self.org, to_organization=liege, name="Crown taxes", percent=20
        )
        extend_loan(creditor=liege, debtor=self.org, principal=10_000, fiat=True)
        member_purse_seed = 500
        from world.currency.services import get_or_create_purse

        transfer(
            amount=member_purse_seed,
            reason="seed",
            to_purse=get_or_create_purse(self.member.character_sheet),
        )
        record_contribution(
            persona=self.member, organization=self.org, amount=200, reason="war chest"
        )

        with mock.patch("world.currency.views._viewer_persona", return_value=self.member):
            response = self._get()

        assert response.status_code == 200
        data = response.json()
        assert data["balance"] == 15_200  # 5000 seed + 10000 loan + 200 contribution
        assert data["graft_pct"] == 10
        assert len(data["income_streams"]) == 1
        assert data["debts"][0]["principal"] == 10_000
        assert data["obligations"][0]["percent"] == 20
        assert data["contributions"][0]["amount"] == 200
        assert any(row["direction"] == "in" for row in data["ledger"])
        for section in ("income_streams", "debts", "obligations", "contributions", "ledger"):
            assert all(isinstance(row["id"], int) for row in data[section])

    def test_non_member_denied(self) -> None:
        with mock.patch("world.currency.views._viewer_persona", return_value=self.outsider):
            response = self._get()
        assert response.status_code == 403

    def test_no_persona_denied(self) -> None:
        with mock.patch("world.currency.views._viewer_persona", return_value=None):
            response = self._get()
        assert response.status_code == 403

    def test_unknown_org_404(self) -> None:
        with mock.patch("world.currency.views._viewer_persona", return_value=self.member):
            response = self._get(org_id=999_999)
        assert response.status_code == 404

    def test_unauthenticated_denied(self) -> None:
        self.client.force_authenticate(user=None)
        response = self._get()
        assert response.status_code in (401, 403)

    def test_list_is_viewer_shelf(self) -> None:
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )

        second_org = OrganizationFactory()
        OrganizationMembershipFactory(persona=self.member, organization=second_org, rank=1)
        # An org the viewer does NOT belong to must never appear on the shelf.
        OrganizationFactory()

        with mock.patch("world.currency.views._viewer_persona", return_value=self.member):
            response = self.client.get("/api/currency/org-books/")

        assert response.status_code == 200
        rows = response.json()
        assert [row["organization_id"] for row in rows] == [second_org.pk, self.org.pk]
        assert rows[0]["rank"] == 1
        assert rows[0]["organization_name"] == second_org.name
        assert rows[0]["rank_title"] == second_org.get_rank_title(1)

    def test_list_without_persona_is_empty(self) -> None:
        with mock.patch("world.currency.views._viewer_persona", return_value=None):
            response = self.client.get("/api/currency/org-books/")
        assert response.status_code == 200
        assert response.json() == []

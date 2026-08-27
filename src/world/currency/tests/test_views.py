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


class OrgVaultEventsApiTests(TestCase):
    """GET /org-books/{org}/vault-events/ — the item-vault audit trail (#2540)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.items.factories import ItemInstanceFactory
        from world.items.services.org_vault import get_or_create_org_vault
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )

        cls.user = AccountFactory(username="vault_events_user")
        cls.org = OrganizationFactory()
        cls.member = PersonaFactory()
        cls.outsider = PersonaFactory()
        OrganizationMembershipFactory(persona=cls.member, organization=cls.org, rank=3)
        cls.vault = get_or_create_org_vault(cls.org)
        cls.item = ItemInstanceFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _get(self, org_id=None):
        return self.client.get(f"/api/currency/org-books/{org_id or self.org.pk}/vault-events/")

    def _event(self, kind, *, item=None, actor=None, reason=""):
        from world.items.org_vault_models import OrgVaultEvent

        return OrgVaultEvent.objects.create(
            vault=self.vault, item_instance=item, kind=kind, actor_persona=actor, reason=reason
        )

    def test_member_sees_deposit_and_withdraw_events_newest_first(self) -> None:
        from world.items.constants import OrgVaultEventKind

        deposit = self._event(OrgVaultEventKind.DEPOSIT, item=self.item, actor=self.member)
        withdraw = self._event(OrgVaultEventKind.WITHDRAW, item=self.item, actor=self.member)

        with mock.patch("world.currency.views._viewer_persona", return_value=self.member):
            response = self._get()

        assert response.status_code == 200
        rows = response.json()
        assert [row["id"] for row in rows] == [withdraw.pk, deposit.pk]
        assert rows[0]["kind"] == "withdraw"
        assert rows[0]["item_name"] == self.item.display_name
        assert rows[0]["actor_persona_name"] == self.member.name
        assert rows[1]["kind"] == "deposit"

    def test_non_member_denied(self) -> None:
        from world.items.constants import OrgVaultEventKind

        self._event(OrgVaultEventKind.DEPOSIT, item=self.item, actor=self.member)
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

    def test_capped_at_fifty(self) -> None:
        from world.items.constants import OrgVaultEventKind

        for _ in range(55):
            self._event(OrgVaultEventKind.DEPOSIT, item=self.item, actor=self.member)

        with mock.patch("world.currency.views._viewer_persona", return_value=self.member):
            response = self._get()

        assert response.status_code == 200
        assert len(response.json()) == 50

    def test_deleted_item_and_actor_show_as_none(self) -> None:
        from world.items.constants import OrgVaultEventKind

        self._event(OrgVaultEventKind.DEPOSIT, item=None, actor=None)

        with mock.patch("world.currency.views._viewer_persona", return_value=self.member):
            response = self._get()

        row = response.json()[0]
        assert row["item_name"] is None
        assert row["actor_persona_name"] is None


class OrgVaultEventsAuditGapTests(TestCase):
    """The embezzlement branch books NO vault event — the discovery hook (#2540 ruling).

    A kept item stays invisible on the audit trail; only the honest deposits in the
    same resolution show up. This is the exact story the reader exists to serve: the
    gap between a collection tally and what actually landed in the vault.
    """

    def setUp(self) -> None:
        from world.consent.constants import ConsentMode
        from world.consent.factories import SocialConsentCategoryFactory
        from world.items.factories import ItemInstanceFactory
        from world.items.org_vault_models import VaultTransit
        from world.items.services.org_vault import get_or_create_org_vault
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )

        self.user = AccountFactory(username="audit_gap_user")
        self.org = OrganizationFactory()
        self.carrier = PersonaFactory()
        OrganizationMembershipFactory(persona=self.carrier, organization=self.org, rank=3)
        vault = get_or_create_org_vault(self.org)
        self.kept_item = ItemInstanceFactory(holder_character_sheet=self.carrier.character_sheet)
        self.deposited_item = ItemInstanceFactory(
            holder_character_sheet=self.carrier.character_sheet
        )
        for item in (self.kept_item, self.deposited_item):
            VaultTransit.objects.create(
                vault=vault,
                item_instance=item,
                carrier_character_sheet=self.carrier.character_sheet,
            )
        entry = RosterEntryFactory(character_sheet=self.carrier.character_sheet)
        RosterTenureFactory(roster_entry=entry)
        # The carrier is the org's sole active piloted member — the topmost piloted
        # stakeholder, so their own embezzlement double-gate self-resolves (#2540 ruling).
        character = self.carrier.character_sheet.character
        character.db_account = AccountFactory()
        character.save(update_fields=["db_account"])
        SocialConsentCategoryFactory(key="embezzlement", default_mode=ConsentMode.ALLOWLIST)

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_kept_item_invisible_deposit_still_shows(self) -> None:
        from world.items.services.org_vault import resolve_vault_transit

        resolve_vault_transit(
            organization=self.org,
            carrier_persona=self.carrier,
            keep_item_ids=[self.kept_item.pk],
        )

        with mock.patch("world.currency.views._viewer_persona", return_value=self.carrier):
            response = self.client.get(f"/api/currency/org-books/{self.org.pk}/vault-events/")

        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1  # only the honest deposit — the kept stone leaves no trace here
        assert rows[0]["kind"] == "deposit"
        assert rows[0]["item_name"] == self.deposited_item.display_name


class OrgBooksActivePersonaLeakTests(TestCase):
    """#981 end-to-end: books follow the worn face, never leak the other faces."""

    def setUp(self) -> None:
        from types import SimpleNamespace

        from rest_framework.test import APIRequestFactory, force_authenticate

        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.currency.views import OrgBooksViewSet
        from world.scenes.constants import PersonaType
        from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.primary = self.sheet.primary_persona  # NOT a member
        self.alt = PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED
        )  # member
        self.org = OrganizationFactory()
        OrganizationMembershipFactory(persona=self.alt, organization=self.org, rank=3)
        self._factory = APIRequestFactory()
        self._view = OrgBooksViewSet.as_view({"get": "retrieve"})
        self._SimpleNamespace = SimpleNamespace
        self._force_authenticate = force_authenticate

    def _get_books(self):
        request = self._factory.get(f"/api/currency/org-books/{self.org.pk}/")
        user = self._SimpleNamespace(is_authenticated=True, is_staff=False, puppet=self.character)
        self._force_authenticate(request, user=user)
        return self._view(request, pk=str(self.org.pk))

    def test_primary_face_cannot_see_the_alts_org_books(self):
        # On the primary (not a member) → denied. The alt's org membership must
        # not be reachable while wearing the primary's face.
        self.assertEqual(self._get_books().status_code, 403)

    def test_switching_to_the_member_face_opens_its_books(self):
        from world.scenes.services import set_active_persona

        set_active_persona(self.sheet, self.alt)
        self.assertEqual(self._get_books().status_code, 200)

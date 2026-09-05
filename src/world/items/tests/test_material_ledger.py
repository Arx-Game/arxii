"""Steward material grants + the house-set asking price (#696 gap 6).

``grant_material_stock`` is the discretionary org-to-one-member movement (gated on
``can_steward_org``, audited as a GRANT ``OrgMaterialLedgerEntry``);
``set_asking_price`` is the same-gated per-category liquidation rate the auto-sell
pays. The auto-sell's own pricing/SALE-row coverage lives in
``world.currency.tests.test_auto_sell_materials`` (extending that module's fixtures
rather than duplicating them here).
"""

from __future__ import annotations

from django.test import TestCase

from world.items.constants import (
    DEFAULT_ASKING_PRICE_PCT,
    MAX_ASKING_PRICE_PCT,
    OrgMaterialLedgerKind,
)
from world.items.exceptions import (
    AskingPriceOutOfBounds,
    GrantRecipientNotMember,
    InsufficientMaterialStock,
    MaterialStewardshipRequired,
)
from world.items.factories import MaterialCategoryFactory
from world.items.gems.buckets import material_value
from world.items.materials_models import OrgMaterialLedgerEntry, OrgMaterialStock
from world.items.services.org_materials import grant_material_stock, set_asking_price
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.constants import DOMAIN_STEWARD_OFFICE
from world.societies.office_services import appoint_office


class MaterialLedgerTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory(name="House Westrock")
        cls.category = MaterialCategoryFactory(name="Cordwood")
        cls.leader = PersonaFactory()
        cls.member = PersonaFactory()
        cls.outsider = PersonaFactory()
        OrganizationMembershipFactory(organization=cls.org, persona=cls.leader, rank=1)
        OrganizationMembershipFactory(organization=cls.org, persona=cls.member)

    def _stock(self, value: int) -> OrgMaterialStock:
        return OrgMaterialStock.objects.create(
            organization=self.org, material_category=self.category, value=value
        )


class GrantMaterialStockTests(MaterialLedgerTestBase):
    def test_grant_debits_stock_and_credits_member_with_one_grant_row(self) -> None:
        stock = self._stock(1000)
        recipient_sheet = self.member.character_sheet
        entry = grant_material_stock(
            organization=self.org,
            material_category=self.category,
            value=400,
            to_sheet=recipient_sheet,
            granted_by=self.leader,
        )
        stock.refresh_from_db()
        self.assertEqual(stock.value, 600)
        self.assertEqual(material_value(recipient_sheet, self.category), 400)
        self.assertEqual(entry.kind, OrgMaterialLedgerKind.GRANT)
        self.assertEqual(entry.value, 400)
        self.assertEqual(entry.counterparty_sheet, recipient_sheet)
        self.assertEqual(OrgMaterialLedgerEntry.objects.filter(organization=self.org).count(), 1)

    def test_steward_office_holder_may_grant(self) -> None:
        steward = PersonaFactory()
        OrganizationMembershipFactory(organization=self.org, persona=steward)
        appoint_office(organization=self.org, slug=DOMAIN_STEWARD_OFFICE, holder=steward)
        self._stock(500)
        entry = grant_material_stock(
            organization=self.org,
            material_category=self.category,
            value=100,
            to_sheet=self.member.character_sheet,
            granted_by=steward,
        )
        self.assertEqual(entry.kind, OrgMaterialLedgerKind.GRANT)

    def test_short_stock_raises_and_writes_nothing(self) -> None:
        stock = self._stock(300)
        recipient_sheet = self.member.character_sheet
        with self.assertRaises(InsufficientMaterialStock):
            grant_material_stock(
                organization=self.org,
                material_category=self.category,
                value=400,
                to_sheet=recipient_sheet,
                granted_by=self.leader,
            )
        stock.refresh_from_db()
        self.assertEqual(stock.value, 300)
        self.assertEqual(material_value(recipient_sheet, self.category), 0)
        self.assertFalse(OrgMaterialLedgerEntry.objects.filter(organization=self.org).exists())

    def test_missing_stock_row_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(InsufficientMaterialStock):
            grant_material_stock(
                organization=self.org,
                material_category=self.category,
                value=1,
                to_sheet=self.member.character_sheet,
                granted_by=self.leader,
            )
        self.assertFalse(OrgMaterialLedgerEntry.objects.filter(organization=self.org).exists())

    def test_non_member_recipient_refused(self) -> None:
        stock = self._stock(1000)
        with self.assertRaises(GrantRecipientNotMember):
            grant_material_stock(
                organization=self.org,
                material_category=self.category,
                value=100,
                to_sheet=self.outsider.character_sheet,
                granted_by=self.leader,
            )
        stock.refresh_from_db()
        self.assertEqual(stock.value, 1000)
        self.assertFalse(OrgMaterialLedgerEntry.objects.filter(organization=self.org).exists())

    def test_non_administrator_refused(self) -> None:
        stock = self._stock(1000)
        with self.assertRaises(MaterialStewardshipRequired):
            grant_material_stock(
                organization=self.org,
                material_category=self.category,
                value=100,
                to_sheet=self.member.character_sheet,
                granted_by=self.member,  # base member, no leadership rank, no office
            )
        stock.refresh_from_db()
        self.assertEqual(stock.value, 1000)
        self.assertFalse(OrgMaterialLedgerEntry.objects.filter(organization=self.org).exists())

    def test_non_positive_value_refused(self) -> None:
        self._stock(1000)
        with self.assertRaises(ValueError):
            grant_material_stock(
                organization=self.org,
                material_category=self.category,
                value=0,
                to_sheet=self.member.character_sheet,
                granted_by=self.leader,
            )


class SetAskingPriceTests(MaterialLedgerTestBase):
    def test_sets_the_price_on_an_existing_stock_row(self) -> None:
        stock = self._stock(1000)
        self.assertEqual(stock.asking_price_pct, DEFAULT_ASKING_PRICE_PCT)
        returned = set_asking_price(
            organization=self.org, material_category=self.category, pct=75, by=self.leader
        )
        self.assertEqual(returned.pk, stock.pk)
        stock.refresh_from_db()
        self.assertEqual(stock.asking_price_pct, 75)

    def test_creates_a_zero_value_row_when_the_category_has_no_stock_yet(self) -> None:
        stock = set_asking_price(
            organization=self.org, material_category=self.category, pct=10, by=self.leader
        )
        self.assertEqual(stock.value, 0)
        self.assertEqual(stock.asking_price_pct, 10)

    def test_bounds_are_inclusive_zero_to_max(self) -> None:
        for pct in (0, MAX_ASKING_PRICE_PCT):
            stock = set_asking_price(
                organization=self.org, material_category=self.category, pct=pct, by=self.leader
            )
            self.assertEqual(stock.asking_price_pct, pct)
        for pct in (-1, MAX_ASKING_PRICE_PCT + 1):
            with self.assertRaises(AskingPriceOutOfBounds):
                set_asking_price(
                    organization=self.org,
                    material_category=self.category,
                    pct=pct,
                    by=self.leader,
                )

    def test_non_administrator_refused(self) -> None:
        with self.assertRaises(MaterialStewardshipRequired):
            set_asking_price(
                organization=self.org, material_category=self.category, pct=50, by=self.member
            )

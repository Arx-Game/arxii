"""Deleting a purse's or treasury's holder keeps the money history (#4467).

``CurrencyTransfer`` is the audit ledger. Its four holder foreign keys are SET_NULL,
and ``currency_transfer_not_void`` used to read those same columns, so deleting a
character sheet or organization that minted or spent money asked the database to
null the transfer's only end and the delete failed. The owner ruled the history
stays: each transfer snapshots who each side was, so the other party's ledger still
reads correctly. These tests go through the admin delete views staff use.
"""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.currency.constants import HolderKind
from world.currency.models import CurrencyTransfer
from world.currency.services import get_or_create_purse, get_or_create_treasury, transfer
from world.societies.factories import OrganizationFactory
from world.societies.models import Organization


class HolderDeletionKeepsLedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-1")

    def setUp(self) -> None:
        self.client.force_login(self.root)

    def _delete(self, url_name: str, pk: int) -> None:
        url = reverse(url_name, args=(pk,))
        resp = self.client.post(url, {"post": "yes"})
        self.assertEqual(resp.status_code, 302)

    def test_deleting_a_sheet_that_minted_money_keeps_the_mint(self) -> None:
        sheet = CharacterSheetFactory()
        name = sheet.primary_persona.name
        row = transfer(amount=500, reason="mission reward", to_purse=get_or_create_purse(sheet))

        self._delete("admin:arxii_charactersheet_delete", sheet.pk)

        self.assertFalse(CharacterSheet.objects.filter(pk=sheet.pk).exists())
        row = CurrencyTransfer.objects.get(pk=row.pk)
        self.assertIsNone(row.to_purse)
        self.assertEqual(row.to_holder_kind, HolderKind.PURSE)
        self.assertEqual(row.to_holder_name, name)
        self.assertEqual(row.from_holder_kind, "")

    def test_deleting_a_sheet_that_spent_money_keeps_the_sink(self) -> None:
        sheet = CharacterSheetFactory()
        name = sheet.primary_persona.name
        purse = get_or_create_purse(sheet)
        transfer(amount=500, reason="seed", to_purse=purse)
        spend = transfer(amount=200, reason="upkeep", from_purse=purse)

        self._delete("admin:arxii_charactersheet_delete", sheet.pk)

        spend = CurrencyTransfer.objects.get(pk=spend.pk)
        self.assertEqual(spend.from_holder_kind, HolderKind.PURSE)
        self.assertEqual(spend.from_holder_name, name)
        self.assertEqual(spend.to_holder_kind, "")

    def test_the_other_side_still_reads_who_the_deleted_holder_was(self) -> None:
        payer, payee = CharacterSheetFactory(), CharacterSheetFactory()
        payer_purse = get_or_create_purse(payer)
        transfer(amount=500, reason="seed", to_purse=payer_purse)
        row = transfer(
            amount=100,
            reason="payment",
            from_purse=payer_purse,
            to_purse=get_or_create_purse(payee),
        )
        payer_name = payer.primary_persona.name

        self._delete("admin:arxii_charactersheet_delete", payer.pk)

        row = CurrencyTransfer.objects.get(pk=row.pk)
        self.assertIsNone(row.from_purse)
        self.assertEqual(row.from_holder_name, payer_name)
        self.assertEqual(row.to_purse, payee.purse)
        self.assertEqual(row.to_holder_kind, HolderKind.PURSE)

    def test_deleting_an_organization_that_moved_money_keeps_the_ledger(self) -> None:
        org = OrganizationFactory(name="House Veyrane")
        sheet = CharacterSheetFactory()
        treasury = get_or_create_treasury(org)
        mint = transfer(amount=900, reason="tithe", to_treasury=treasury)
        spend = transfer(amount=300, reason="levy", from_treasury=treasury)
        gift = transfer(
            amount=100,
            reason="stipend",
            from_treasury=treasury,
            to_purse=get_or_create_purse(sheet),
        )

        self._delete("admin:arxii_organization_delete", org.pk)

        self.assertFalse(Organization.objects.filter(pk=org.pk).exists())
        mint, spend, gift = (CurrencyTransfer.objects.get(pk=r.pk) for r in (mint, spend, gift))
        self.assertEqual(
            (mint.to_holder_kind, mint.to_holder_name), (HolderKind.TREASURY, org.name)
        )
        self.assertEqual(
            (spend.from_holder_kind, spend.from_holder_name), (HolderKind.TREASURY, org.name)
        )
        self.assertEqual(gift.from_holder_name, "House Veyrane")
        self.assertEqual(gift.to_purse, sheet.purse)

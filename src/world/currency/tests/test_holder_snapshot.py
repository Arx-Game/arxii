"""Each CurrencyTransfer snapshots who its holders were (#4467, step one).

The snapshot is what lets the ledger keep reading correctly once a character sheet or
organization is gone. The constraint swap that makes the delete itself succeed is a
later step; these tests cover only what is written and kept.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.constants import HolderKind
from world.currency.models import CurrencyTransfer
from world.currency.services import get_or_create_purse, get_or_create_treasury, transfer
from world.societies.factories import OrganizationFactory


class HolderSnapshotTests(TestCase):
    def test_a_mint_into_a_purse_names_only_the_destination(self) -> None:
        sheet = CharacterSheetFactory()
        row = transfer(amount=500, reason="reward", to_purse=get_or_create_purse(sheet))
        self.assertEqual(row.from_holder_kind, "")
        self.assertEqual(row.to_holder_kind, HolderKind.PURSE)
        self.assertEqual(row.to_holder_name, sheet.primary_persona.name)

    def test_a_treasury_to_purse_transfer_names_both_sides(self) -> None:
        org = OrganizationFactory(name="House Veyrane")
        sheet = CharacterSheetFactory()
        treasury = get_or_create_treasury(org)
        transfer(amount=900, reason="tithe", to_treasury=treasury)
        row = transfer(
            amount=100,
            reason="stipend",
            from_treasury=treasury,
            to_purse=get_or_create_purse(sheet),
        )
        self.assertEqual((row.from_holder_kind, row.from_holder_name), ("treasury", org.name))
        self.assertEqual(row.to_holder_kind, HolderKind.PURSE)

    def test_a_sheet_with_no_primary_persona_still_moves_money(self) -> None:
        sheet = CharacterSheetFactory()
        sheet.personas.all().delete()
        row = transfer(amount=5, reason="mint", to_purse=get_or_create_purse(sheet))
        self.assertEqual(row.to_holder_name, f"Character {sheet.pk}")

    def test_a_later_save_keeps_the_name_the_holder_had_at_the_time(self) -> None:
        sheet = CharacterSheetFactory()
        row = transfer(amount=5, reason="mint", to_purse=get_or_create_purse(sheet))
        before = row.to_holder_name
        persona = sheet.primary_persona
        persona.name = "Renamed Afterwards"
        persona.save()
        row.save()
        self.assertEqual(CurrencyTransfer.objects.get(pk=row.pk).to_holder_name, before)

    def test_a_transfer_with_no_end_at_all_is_still_refused(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            CurrencyTransfer.objects.create(amount=5, reason="void")

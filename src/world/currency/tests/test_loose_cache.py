"""Loose coin caches (#1909): arbitrary-value physical money, fee-free."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.constants import Denomination
from world.currency.models import CurrencyInstrumentDetails
from world.currency.services import (
    get_or_create_purse,
    mint_loose_cache,
    redeem_instrument,
    transfer,
)


class LooseCacheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.purse = get_or_create_purse(cls.sheet)
        transfer(amount=1_000, reason="test seed", to_purse=cls.purse)

    def test_mint_loose_cache_conserves_value_no_fee(self):
        instance = mint_loose_cache(amount=350, holder_sheet=self.sheet, from_purse=self.purse)
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 650)  # exactly 350 left, zero fee
        details = CurrencyInstrumentDetails.objects.get(item_instance=instance)
        self.assertEqual(details.denomination, Denomination.LOOSE)
        self.assertEqual(details.face_value, 350)
        self.assertEqual(instance.holder_character_sheet, self.sheet)

    def test_mint_loose_cache_rejects_nonpositive_and_insufficient(self):
        with self.assertRaises(ValidationError):
            mint_loose_cache(amount=0, holder_sheet=self.sheet, from_purse=self.purse)
        with self.assertRaises(ValidationError):
            mint_loose_cache(amount=999_999, holder_sheet=self.sheet, from_purse=self.purse)

    def test_deposit_via_redeem_instrument_roundtrip(self):
        instance = mint_loose_cache(amount=350, holder_sheet=self.sheet, from_purse=self.purse)
        redeem_instrument(instance=instance, to_purse=self.purse)
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 1_000)
        self.assertEqual(CurrencyInstrumentDetails.objects.count(), 0)  # instrument consumed

"""Tests for personal asset income collection (#2294).

Mirrors test_collection.py for orgs. Outcome bands forced via the
checks test helper — magnitudes mirror the PLACEHOLDER constants.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.assets.factories import NPCAssetFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.models import CurrencyTransfer
from world.currency.services import (
    collect_asset_income,
    get_or_create_purse,
)
from world.traits.factories import CheckOutcomeFactory


class AssetCollectionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        CheckTypeFactory(name="Tax Collection")

    def setUp(self) -> None:
        self.asset = NPCAssetFactory()
        self.asset.weekly_income = 1000
        self.asset.uncollected_pool = 1000
        self.asset.save(update_fields=["weekly_income", "uncollected_pool"])

    def _purse_balance(self) -> int:
        purse = get_or_create_purse(self.sheet)
        purse.refresh_from_db()
        return purse.balance

    def _collect(self, success_level: int):
        outcome = CheckOutcomeFactory(
            name=f"asset_collect_{success_level}", success_level=success_level
        )
        with force_check_outcome(outcome):
            return collect_asset_income(asset=self.asset, character_sheet=self.sheet)

    def test_clean_collection_lands_full_amount(self) -> None:
        result = self._collect(1)
        self.assertEqual(result.gathered, 1000)
        self.assertEqual(result.landed, 1000)  # 100% band, no graft
        self.assertEqual(result.graft_leak, 0)
        self.assertEqual(self._purse_balance(), 1000)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.uncollected_pool, 0)

    def test_critical_collection_carries_goodwill_bonus(self) -> None:
        result = self._collect(2)
        self.assertEqual(result.landed, 1100)  # 110% band
        self.assertEqual(self._purse_balance(), 1100)

    def test_skim_band(self) -> None:
        result = self._collect(0)
        self.assertEqual(result.landed, 850)  # 85% band
        self.assertEqual(self._purse_balance(), 850)
        self.assertGreater(result.stolen, 0)

    def test_waylaid_band(self) -> None:
        result = self._collect(-1)
        self.assertEqual(result.landed, 350)  # 35% band
        self.assertEqual(self._purse_balance(), 350)

    def test_catastrophe_loses_everything(self) -> None:
        result = self._collect(-2)
        self.assertTrue(result.catastrophe)
        self.assertEqual(result.landed, 0)
        self.assertEqual(self._purse_balance(), 0)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.uncollected_pool, 0)  # gone

    def test_empty_pool_refuses(self) -> None:
        self.asset.uncollected_pool = 0
        self.asset.save(update_fields=["uncollected_pool"])
        with self.assertRaises(ValidationError):
            collect_asset_income(asset=self.asset, character_sheet=self.sheet)

    def test_transfer_audit_row_created(self) -> None:
        self._collect(1)
        transfers = CurrencyTransfer.objects.filter(
            to_purse__character_sheet=self.sheet,
            reason="asset income collection",
        )
        self.assertEqual(transfers.count(), 1)
        self.assertEqual(transfers.first().amount, 1000)

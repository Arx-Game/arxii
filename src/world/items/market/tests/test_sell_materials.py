"""Personal material sale (#2540 slice 2): the sell-to-market face of the material buckets.

Task 1 built ``spend_materials``; this is its personal seller-facing use — mint-to-purse
for bulk material bucket value, mirroring the fence's mint-to-purse convention
(``world.items.market.services.sell_to_fence``, #2862) rather than a player-to-player trade.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse
from world.items.exceptions import InsufficientMaterialStock
from world.items.factories import MaterialBucketFactory, MaterialCategoryFactory
from world.items.gems.buckets import material_value
from world.items.market.services import MATERIAL_SALE_RATE_PCT, MarketServiceError, sell_materials
from world.items.materials_models import MaterialBucket


class SellMaterialsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.category = MaterialCategoryFactory(name="Cordwood")

    def test_sells_bucket_value_at_the_rate_into_the_purse(self) -> None:
        MaterialBucketFactory(
            character_sheet=self.sheet, material_category=self.category, value=1000
        )
        coins = sell_materials(
            seller_sheet=self.sheet, material_category=self.category, amount=1000
        )
        self.assertEqual(coins, 1000 * MATERIAL_SALE_RATE_PCT // 100)
        self.assertEqual(material_value(self.sheet, self.category), 0)
        self.assertEqual(get_or_create_purse(self.sheet).balance, coins)

    def test_partial_sale_leaves_the_remainder_in_the_bucket(self) -> None:
        MaterialBucketFactory(
            character_sheet=self.sheet, material_category=self.category, value=1000
        )
        coins = sell_materials(seller_sheet=self.sheet, material_category=self.category, amount=300)
        self.assertEqual(coins, 300 * MATERIAL_SALE_RATE_PCT // 100)
        self.assertEqual(material_value(self.sheet, self.category), 700)

    def test_insufficient_bucket_raises_and_moves_nothing(self) -> None:
        MaterialBucketFactory(character_sheet=self.sheet, material_category=self.category, value=20)
        with self.assertRaises(MarketServiceError) as ctx:
            sell_materials(seller_sheet=self.sheet, material_category=self.category, amount=50)
        self.assertEqual(ctx.exception.user_message, InsufficientMaterialStock.user_message)
        self.assertEqual(material_value(self.sheet, self.category), 20)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 0)

    def test_amount_too_small_to_pay_a_copper_is_refused_and_moves_nothing(self) -> None:
        MaterialBucketFactory(character_sheet=self.sheet, material_category=self.category, value=10)
        with self.assertRaises(MarketServiceError):
            sell_materials(seller_sheet=self.sheet, material_category=self.category, amount=1)
        self.assertEqual(material_value(self.sheet, self.category), 10)  # bucket untouched

    def test_transfer_failure_rolls_back_the_bucket_debit(self) -> None:
        """A crash between the spend and the mint must not leave a spent-but-unpaid seller
        (the atomicity bug the review round flagged: sell_materials had no
        @transaction.atomic, so spend_materials and transfer each committed independently)."""
        MaterialBucketFactory(
            character_sheet=self.sheet, material_category=self.category, value=1000
        )
        with (
            patch("world.currency.services.transfer", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            sell_materials(seller_sheet=self.sheet, material_category=self.category, amount=500)
        # SharedMemoryModel keeps object identity across queries (ADR-0008) — the in-process
        # bucket instance was mutated before the raise, so a fresh read must bypass that
        # cache to see the true post-rollback DB row (see the sharedmemory-model skill).
        MaterialBucket.flush_instance_cache()
        self.assertEqual(material_value(self.sheet, self.category), 1000)  # rolled back
        self.assertEqual(get_or_create_purse(self.sheet).balance, 0)

    def test_multiple_categories_sell_independently(self) -> None:
        other_category = MaterialCategoryFactory(name="Iron Ore")
        MaterialBucketFactory(
            character_sheet=self.sheet, material_category=self.category, value=500
        )
        MaterialBucketFactory(
            character_sheet=self.sheet, material_category=other_category, value=200
        )
        coins_a = sell_materials(
            seller_sheet=self.sheet, material_category=self.category, amount=500
        )
        coins_b = sell_materials(
            seller_sheet=self.sheet, material_category=other_category, amount=200
        )
        self.assertEqual(coins_a, 500 * MATERIAL_SALE_RATE_PCT // 100)
        self.assertEqual(coins_b, 200 * MATERIAL_SALE_RATE_PCT // 100)
        self.assertEqual(material_value(self.sheet, self.category), 0)
        self.assertEqual(material_value(self.sheet, other_category), 0)
        self.assertEqual(get_or_create_purse(self.sheet).balance, coins_a + coins_b)

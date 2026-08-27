"""Org auto-sell of excess materials (#2540 slice 2).

The org-level analogue of ``market.sell_materials``: any ``OrgMaterialStock`` row over
``MATERIAL_AUTO_SELL_THRESHOLD`` has its excess liquidated into the treasury at
``MATERIAL_SALE_RATE_PCT`` (the same rate the personal sell action pays). Direct unit
coverage of ``auto_sell_excess_materials`` — the ``collect_and_distribute`` wiring lives
in ``test_distribution_dispatch.py``.
"""

from __future__ import annotations

from django.test import TestCase

from world.currency.constants import MATERIAL_AUTO_SELL_THRESHOLD
from world.currency.services import auto_sell_excess_materials, get_or_create_treasury
from world.items.factories import MaterialCategoryFactory
from world.items.market.services import MATERIAL_SALE_RATE_PCT
from world.items.materials_models import OrgMaterialStock
from world.societies.factories import OrganizationFactory


class AutoSellExcessMaterialsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.category = MaterialCategoryFactory(name="Cordwood")
        cls.other_category = MaterialCategoryFactory(name="Iron Ore")

    def _stock(self, category, value: int) -> OrgMaterialStock:
        return OrgMaterialStock.objects.create(
            organization=self.org, material_category=category, value=value
        )

    def test_no_stock_rows_is_a_noop(self) -> None:
        self.assertEqual(auto_sell_excess_materials(organization=self.org), 0)

    def test_stock_at_threshold_exactly_sells_nothing(self) -> None:
        stock = self._stock(self.category, MATERIAL_AUTO_SELL_THRESHOLD)
        coins = auto_sell_excess_materials(organization=self.org)
        self.assertEqual(coins, 0)
        stock.refresh_from_db()
        self.assertEqual(stock.value, MATERIAL_AUTO_SELL_THRESHOLD)

    def test_stock_under_threshold_sells_nothing(self) -> None:
        stock = self._stock(self.category, MATERIAL_AUTO_SELL_THRESHOLD - 1)
        coins = auto_sell_excess_materials(organization=self.org)
        self.assertEqual(coins, 0)
        stock.refresh_from_db()
        self.assertEqual(stock.value, MATERIAL_AUTO_SELL_THRESHOLD - 1)

    def test_excess_over_threshold_sells_only_the_excess(self) -> None:
        stock = self._stock(self.category, MATERIAL_AUTO_SELL_THRESHOLD + 1000)
        coins = auto_sell_excess_materials(organization=self.org)
        self.assertEqual(coins, 1000 * MATERIAL_SALE_RATE_PCT // 100)
        stock.refresh_from_db()
        self.assertEqual(stock.value, MATERIAL_AUTO_SELL_THRESHOLD)
        treasury = get_or_create_treasury(self.org)
        treasury.refresh_from_db()
        self.assertEqual(treasury.balance, coins)

    def test_multiple_categories_liquidate_independently(self) -> None:
        stock_a = self._stock(self.category, MATERIAL_AUTO_SELL_THRESHOLD + 1000)
        stock_b = self._stock(self.other_category, MATERIAL_AUTO_SELL_THRESHOLD + 2000)
        coins = auto_sell_excess_materials(organization=self.org)
        self.assertEqual(coins, (1000 + 2000) * MATERIAL_SALE_RATE_PCT // 100)
        stock_a.refresh_from_db()
        stock_b.refresh_from_db()
        self.assertEqual(stock_a.value, MATERIAL_AUTO_SELL_THRESHOLD)
        self.assertEqual(stock_b.value, MATERIAL_AUTO_SELL_THRESHOLD)

    def test_a_worthless_excess_never_blocks_a_siblings_sale(self) -> None:
        # excess=1 -> 1 * 40 // 100 = 0 coppers: skipped rather than debited for nothing.
        stock_tiny = self._stock(self.category, MATERIAL_AUTO_SELL_THRESHOLD + 1)
        stock_big = self._stock(self.other_category, MATERIAL_AUTO_SELL_THRESHOLD + 1000)
        coins = auto_sell_excess_materials(organization=self.org)
        self.assertEqual(coins, 1000 * MATERIAL_SALE_RATE_PCT // 100)
        stock_tiny.refresh_from_db()
        stock_big.refresh_from_db()
        self.assertEqual(stock_tiny.value, MATERIAL_AUTO_SELL_THRESHOLD + 1)  # untouched
        self.assertEqual(stock_big.value, MATERIAL_AUTO_SELL_THRESHOLD)

    def test_other_organizations_stock_is_never_touched(self) -> None:
        other_org = OrganizationFactory()
        other_stock = OrgMaterialStock.objects.create(
            organization=other_org,
            material_category=self.category,
            value=MATERIAL_AUTO_SELL_THRESHOLD + 1000,
        )
        auto_sell_excess_materials(organization=self.org)
        other_stock.refresh_from_db()
        self.assertEqual(other_stock.value, MATERIAL_AUTO_SELL_THRESHOLD + 1000)

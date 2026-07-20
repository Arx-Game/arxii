"""Tests for the gem side of the org collection dispatch (Build 0b, domain-cron collection).

Gems are *lumped with tax collection*: ``collect_org_income`` gathers the org's uncollected
gem pools + Rare-Find stones alongside coin, and the same outcome band + graft + catastrophe
decide what lands. Net common value → the house's ``OrgGemStock``; surviving stones → the
collector's hands; a bad collection loses some. Outcome bands are forced via the checks helper.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.models import OrgIncomeStream
from world.currency.services import (
    accrue_income_stream,
    collect_org_income,
    get_or_create_economics,
)
from world.items.factories import ItemInstanceFactory, MaterialCategoryFactory
from world.items.gems.models import OrgGemStock, PendingRareFind, StreamCommonGemPool
from world.societies.factories import OrganizationFactory
from world.traits.factories import CheckOutcomeFactory


class GemCollectionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory(name="House Testvein")
        cls.tier = MaterialCategoryFactory(name="Semiprecious")
        cls.character = CharacterSheetFactory().character
        cls.collector_sheet = cls.character.character_sheet
        CheckTypeFactory(name="Tax Collection")
        economics = get_or_create_economics(cls.org)
        economics.graft_pct = 10
        economics.save(update_fields=["graft_pct"])

    def setUp(self) -> None:
        self.stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Gem Mine", kind="domain_tax", gross_amount=100
        )
        StreamCommonGemPool.objects.create(
            income_stream=self.stream, tier=self.tier, uncollected_value=1000
        )
        self.stones = [ItemInstanceFactory() for _ in range(4)]
        for stone in self.stones:
            PendingRareFind.objects.create(income_stream=self.stream, gem_instance=stone)

    def _collect(self, success_level: int):
        outcome = CheckOutcomeFactory(name=f"collect_{success_level}", success_level=success_level)
        with force_check_outcome(outcome):
            return collect_org_income(organization=self.org, character=self.character)

    def _stock_value(self) -> int:
        stock = OrgGemStock.objects.filter(organization=self.org, tier=self.tier).first()
        return stock.value if stock is not None else 0

    def test_clean_collection_lands_net_common_and_surviving_stones(self) -> None:
        # No coin accrued: the mine's stream has only gems — the dispatch still runs.
        result = self._collect(1)  # 100% band, 10% graft
        # Common: 1000 → collected 1000 → net 900 into the house stock.
        self.assertEqual(result.gem_value_landed, 900)
        self.assertEqual(self._stock_value(), 900)
        # Stones ride the same net rate: 4 × 100% × 90% = 3 survive, 1 lost.
        self.assertEqual(result.stones_delivered, 3)
        self.assertEqual(result.stones_lost, 1)
        held = [s for s in self.stones if _reloaded(s) is not None]
        self.assertEqual(len(held), 3)
        for stone in held:
            self.assertEqual(stone.holder_character_sheet_id, self.collector_sheet.pk)
        # Pools zero and pendings resolve regardless of what survived.
        self.assertFalse(PendingRareFind.objects.filter(income_stream=self.stream).exists())
        self.stream.refresh_from_db()
        pool = StreamCommonGemPool.objects.get(income_stream=self.stream, tier=self.tier)
        self.assertEqual(pool.uncollected_value, 0)

    def test_catastrophe_loses_all_common_and_all_stones(self) -> None:
        result = self._collect(-2)
        self.assertTrue(result.catastrophe)
        self.assertEqual(result.gem_value_landed, 0)
        self.assertEqual(result.stones_delivered, 0)
        self.assertEqual(result.stones_lost, 4)
        self.assertEqual(self._stock_value(), 0)
        self.assertEqual(sum(1 for s in self.stones if _reloaded(s) is not None), 0)
        pool = StreamCommonGemPool.objects.get(income_stream=self.stream, tier=self.tier)
        self.assertEqual(pool.uncollected_value, 0)  # the gems are simply gone

    def test_coin_and_gems_ride_the_same_dispatch(self) -> None:
        # Accrue coin too; one dispatch lands both under the same band + graft.
        accrue_income_stream(self.stream)  # gross 100 → uncollected_pool 100
        result = self._collect(1)
        self.assertEqual(result.gathered, 100)  # coin
        self.assertEqual(result.landed, 90)  # coin net of graft
        self.assertEqual(result.gem_value_landed, 900)  # gems net of graft
        self.assertEqual(self._stock_value(), 900)

    def test_delivered_stones_are_minted_as_vault_transit(self) -> None:
        # #2540 ruling: collection is a mission with a return leg — every stone that
        # reaches the collector's hands is owed to the house vault via a transit row.
        from world.items.org_vault_models import VaultTransit

        self._collect(1)  # 3 of 4 stones survive to the collector
        transits = VaultTransit.objects.filter(
            vault__organization=self.org, resolved_at__isnull=True
        )
        self.assertEqual(transits.count(), 3)
        for transit in transits:
            self.assertEqual(transit.carrier_character_sheet_id, self.collector_sheet.pk)

    def test_stock_accumulates_across_collections(self) -> None:
        self._collect(1)
        # A second cycle accrues more common value (mutate-then-save, as accrual does — an
        # .update() would bypass the SharedMemoryModel cache), then a second collection stacks it.
        pool = StreamCommonGemPool.objects.get(income_stream=self.stream, tier=self.tier)
        pool.uncollected_value = 1000
        pool.save(update_fields=["uncollected_value"])
        self._collect(1)
        self.assertEqual(self._stock_value(), 1800)  # 900 + 900


def _reloaded(instance):
    """Return the instance re-fetched from the DB, or None if it was deleted."""
    return type(instance).objects.filter(pk=instance.pk).first()

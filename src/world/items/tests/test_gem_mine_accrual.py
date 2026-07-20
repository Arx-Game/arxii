"""Tests for the weekly mine accrual cycle (Build 0b slice 7).

``accrue_mine_cycle`` reads only ``income_stream`` / ``mine_quality`` / ``common_gem_tier``
off the holding, so these unit-test it against a real ``OrgIncomeStream`` and a lightweight
holding stand-in — avoiding the full Domain/Area chain (whose ``areas_areaclosure`` matview
is absent on the local test DB; the real DomainHolding wiring is exercised in CI via the
houses suite).
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from world.currency.models import OrgIncomeStream
from world.items.factories import (
    GemDetailsFactory,
    GemGradeFactory,
    ItemTemplateFactory,
    MaterialCategoryFactory,
)
from world.items.gems.constants import COMMON_VALUE_PER_QUALITY, GemAxis
from world.items.gems.mining import accrue_mine_cycle
from world.items.gems.models import PendingRareFind, StreamCommonGemPool
from world.societies.factories import OrganizationFactory


def _roll(*values):
    it = iter(values)
    return lambda: next(it)


class AccrueMineCycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(1, 5):
            GemGradeFactory(axis=GemAxis.SIZE, sort_order=i, label=f"s{i}", multiplier=Decimal(i))
            GemGradeFactory(axis=GemAxis.PURITY, sort_order=i, label=f"p{i}", multiplier=Decimal(i))
        GemGradeFactory(axis=GemAxis.CUT, sort_order=1, label="uncut", multiplier=Decimal("1.0"))
        for lvl in (1, 3):
            GemDetailsFactory(
                item_template=ItemTemplateFactory(name=f"gem-{lvl}", value=100), quality_level=lvl
            )
        cls.tier = MaterialCategoryFactory(name="Semiprecious")

    def _stream(self):
        return OrgIncomeStream.objects.create(
            organization=OrganizationFactory(name="House Testvein"),
            name="Gem Mine",
            kind="domain_tax",
            gross_amount=100,
        )

    def _holding(self, *, stream=None, mine_quality=10, tier=...):
        return SimpleNamespace(
            income_stream=stream if stream is not None else self._stream(),
            mine_quality=mine_quality,
            common_gem_tier=self.tier if tier is ... else tier,
        )

    def test_common_value_accrues_into_the_stream_pool(self):
        holding = self._holding(mine_quality=10)
        # occurrence roll 99 > chance 11 → no rare find; common = 10 * 50 = 500.
        haul = accrue_mine_cycle(holding=holding, roll=_roll(99))
        self.assertEqual(haul.rare_finds, [])
        pool = StreamCommonGemPool.objects.get(income_stream=holding.income_stream, tier=self.tier)
        self.assertEqual(pool.uncollected_value, 10 * COMMON_VALUE_PER_QUALITY)

    def test_accrual_accumulates_across_cycles(self):
        holding = self._holding(mine_quality=10)
        accrue_mine_cycle(holding=holding, roll=_roll(99))
        accrue_mine_cycle(holding=holding, roll=_roll(99))
        pool = StreamCommonGemPool.objects.get(income_stream=holding.income_stream)
        self.assertEqual(pool.uncollected_value, 2 * 10 * COMMON_VALUE_PER_QUALITY)

    def test_rare_find_becomes_pending_on_the_stream(self):
        holding = self._holding(mine_quality=10)
        # occ 5 (<=11) → find; count 1; per-find type/size/purity 10 each.
        haul = accrue_mine_cycle(holding=holding, roll=_roll(5, 1, 10, 10, 10))
        self.assertEqual(len(haul.rare_finds), 1)
        pending = PendingRareFind.objects.filter(income_stream=holding.income_stream)
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.first().gem_instance, haul.rare_finds[0])
        self.assertIsNone(haul.rare_finds[0].holder_character_sheet_id)  # loose until collected

    def test_no_tier_configured_accrues_nothing(self):
        holding = self._holding(mine_quality=10, tier=None)
        haul = accrue_mine_cycle(holding=holding, roll=_roll(5, 1, 10, 10, 10))
        self.assertEqual(haul.common_value, 0)
        self.assertEqual(haul.rare_finds, [])
        self.assertFalse(
            StreamCommonGemPool.objects.filter(income_stream=holding.income_stream).exists()
        )

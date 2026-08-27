"""Tests for the general per-holding material production cycle (#2540 slice 2).

``accrue_holding_materials`` iterates every ``HoldingMaterialSource`` a holding
carries (BULK and GEM_MINE), so these unit-test it against a real ``OrgIncomeStream``
and a lightweight holding + source stand-in — avoiding the full Domain/Area chain
(whose ``areas_areaclosure`` matview is absent on the local test DB; the real
``DomainHolding`` wiring is exercised in CI via the houses suite and
``world.currency.tests.test_weekly_mine_accrual``).
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from world.currency.models import OrgIncomeStream
from world.items.constants import BULK_YIELD_PER_QUALITY, MaterialSourceKind
from world.items.factories import (
    GemDetailsFactory,
    GemGradeFactory,
    ItemTemplateFactory,
    MaterialCategoryFactory,
)
from world.items.gems.constants import COMMON_VALUE_PER_QUALITY, GemAxis
from world.items.gems.models import PendingRareFind
from world.items.materials_models import StreamMaterialPool
from world.items.materials_production import accrue_holding_materials
from world.societies.factories import OrganizationFactory


def _roll(*values):
    it = iter(values)
    return lambda: next(it)


class _FakeMaterialSources:
    """Stand-in for the ``holding.material_sources`` related manager.

    Mimics the ``.select_related(...)`` chain ``accrue_holding_materials`` runs (the
    result is then iterated directly), without needing a real ``DomainHolding`` row.
    """

    def __init__(self, sources):
        self._sources = sources

    def select_related(self, *_args):
        return self._sources


class AccrueHoldingMaterialsTests(TestCase):
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
        cls.gem_category = MaterialCategoryFactory(name="Semiprecious")
        cls.bulk_category = MaterialCategoryFactory(name="Timber")

    def _stream(self):
        return OrgIncomeStream.objects.create(
            organization=OrganizationFactory(name="House Testvein"),
            name="Holding Production",
            kind="domain_tax",
            gross_amount=100,
        )

    def _source(self, *, category, quality, source_kind):
        return SimpleNamespace(quality=quality, material_category=category, source_kind=source_kind)

    def _holding(self, *, sources, stream=...):
        return SimpleNamespace(
            income_stream=self._stream() if stream is ... else stream,
            material_sources=_FakeMaterialSources(sources),
        )

    def test_bulk_source_accrues_flat_value_into_the_pool(self):
        source = self._source(
            category=self.bulk_category, quality=3, source_kind=MaterialSourceKind.BULK
        )
        holding = self._holding(sources=[source])

        haul = accrue_holding_materials(holding=holding, roll=_roll())

        self.assertEqual(haul.rare_finds, [])
        self.assertEqual(
            haul.common_value_by_category, [(self.bulk_category, 3 * BULK_YIELD_PER_QUALITY)]
        )
        pool = StreamMaterialPool.objects.get(
            income_stream=holding.income_stream, material_category=self.bulk_category
        )
        self.assertEqual(pool.uncollected_value, 3 * BULK_YIELD_PER_QUALITY)

    def test_gem_mine_source_still_rolls_rare_finds(self):
        source = self._source(
            category=self.gem_category, quality=10, source_kind=MaterialSourceKind.GEM_MINE
        )
        holding = self._holding(sources=[source])
        # occ 5 (<= 11 chance) → find; count 1; per-find type/size/purity 10 each.
        haul = accrue_holding_materials(holding=holding, roll=_roll(5, 1, 10, 10, 10))

        self.assertEqual(len(haul.rare_finds), 1)
        self.assertEqual(
            haul.common_value_by_category, [(self.gem_category, 10 * COMMON_VALUE_PER_QUALITY)]
        )
        pending = PendingRareFind.objects.filter(income_stream=holding.income_stream)
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.first().gem_instance, haul.rare_finds[0])
        self.assertIsNone(haul.rare_finds[0].holder_character_sheet_id)  # loose until collected
        pool = StreamMaterialPool.objects.get(
            income_stream=holding.income_stream, material_category=self.gem_category
        )
        self.assertEqual(pool.uncollected_value, 10 * COMMON_VALUE_PER_QUALITY)

    def test_mixed_source_holding_accrues_both(self):
        gem_source = self._source(
            category=self.gem_category, quality=10, source_kind=MaterialSourceKind.GEM_MINE
        )
        bulk_source = self._source(
            category=self.bulk_category, quality=4, source_kind=MaterialSourceKind.BULK
        )
        holding = self._holding(sources=[gem_source, bulk_source])
        # occurrence roll 99 > chance 11 → no rare find on the gem source.
        haul = accrue_holding_materials(holding=holding, roll=_roll(99))

        self.assertEqual(haul.rare_finds, [])
        self.assertEqual(
            haul.common_value_by_category,
            [
                (self.gem_category, 10 * COMMON_VALUE_PER_QUALITY),
                (self.bulk_category, 4 * BULK_YIELD_PER_QUALITY),
            ],
        )
        gem_pool = StreamMaterialPool.objects.get(
            income_stream=holding.income_stream, material_category=self.gem_category
        )
        bulk_pool = StreamMaterialPool.objects.get(
            income_stream=holding.income_stream, material_category=self.bulk_category
        )
        self.assertEqual(gem_pool.uncollected_value, 10 * COMMON_VALUE_PER_QUALITY)
        self.assertEqual(bulk_pool.uncollected_value, 4 * BULK_YIELD_PER_QUALITY)

    def test_accrual_accumulates_across_cycles(self):
        source = self._source(
            category=self.bulk_category, quality=3, source_kind=MaterialSourceKind.BULK
        )
        holding = self._holding(sources=[source])
        accrue_holding_materials(holding=holding, roll=_roll())
        accrue_holding_materials(holding=holding, roll=_roll())
        pool = StreamMaterialPool.objects.get(
            income_stream=holding.income_stream, material_category=self.bulk_category
        )
        self.assertEqual(pool.uncollected_value, 2 * 3 * BULK_YIELD_PER_QUALITY)

    def test_no_income_stream_accrues_nothing(self):
        source = self._source(
            category=self.bulk_category, quality=3, source_kind=MaterialSourceKind.BULK
        )
        holding = self._holding(sources=[source], stream=None)
        haul = accrue_holding_materials(holding=holding, roll=_roll())
        self.assertEqual(haul.common_value_by_category, [])
        self.assertEqual(haul.rare_finds, [])
        self.assertFalse(StreamMaterialPool.objects.exists())

    def test_no_material_sources_accrues_nothing(self):
        holding = self._holding(sources=[])
        haul = accrue_holding_materials(holding=holding, roll=_roll())
        self.assertEqual(haul.common_value_by_category, [])
        self.assertEqual(haul.rare_finds, [])
        self.assertFalse(
            StreamMaterialPool.objects.filter(income_stream=holding.income_stream).exists()
        )

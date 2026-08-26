"""Model smoke tests for HoldingMaterialSource (#2540 slice 2).

Replaces ``DomainHolding.mine_quality``/``common_gem_tier`` with a proper per-category
row so a holding can carry more than one production source. Full mining/collection
integration is covered in ``world.items.tests.test_gem_mine_accrual`` and
``world.currency.tests.test_weekly_mine_accrual``; this file is just the model shape.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.items.constants import MaterialSourceKind
from world.items.factories import MaterialCategoryFactory
from world.societies.houses.factories import DomainHoldingFactory, HoldingMaterialSourceFactory
from world.societies.houses.models import HoldingMaterialSource


class HoldingMaterialSourceModelTests(TestCase):
    def test_source_kind_defaults_to_bulk(self) -> None:
        source = HoldingMaterialSourceFactory()
        self.assertEqual(source.source_kind, MaterialSourceKind.BULK)
        self.assertEqual(source.quality, 1)

    def test_gem_mine_source_kind_roundtrips(self) -> None:
        source = HoldingMaterialSourceFactory(source_kind=MaterialSourceKind.GEM_MINE, quality=5)
        source.refresh_from_db()
        self.assertEqual(source.source_kind, MaterialSourceKind.GEM_MINE)
        self.assertEqual(source.quality, 5)

    def test_unique_per_holding_and_category(self) -> None:
        holding = DomainHoldingFactory()
        material_category = MaterialCategoryFactory()
        HoldingMaterialSource.objects.create(holding=holding, material_category=material_category)
        with self.assertRaises(IntegrityError), transaction.atomic():
            HoldingMaterialSource.objects.create(
                holding=holding, material_category=material_category
            )

    def test_a_holding_may_carry_multiple_sources(self) -> None:
        holding = DomainHoldingFactory()
        one = HoldingMaterialSourceFactory(holding=holding)
        two = HoldingMaterialSourceFactory(holding=holding)
        self.assertEqual(holding.material_sources.count(), 2)
        self.assertIn(one, holding.material_sources.all())
        self.assertIn(two, holding.material_sources.all())

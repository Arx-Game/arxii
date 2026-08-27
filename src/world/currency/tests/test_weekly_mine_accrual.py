"""Weekly mine accrual rides the economy rollover (#2540 Build 0b wiring)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.currency.services import _weekly_mine_accrual
from world.items.constants import MaterialSourceKind
from world.items.factories import MaterialCategoryFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.factories import HoldingMaterialSourceFactory
from world.societies.houses.models import HoldingKind
from world.societies.houses.services import add_holding, create_domain


class WeeklyMineAccrualTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        org = OrganizationFactory()
        domain = create_domain(area=AreaFactory(), name="Gemvale", owner_org=org)
        kind = HoldingKind.objects.create(name="Mine", stream_kind="domain_tax", base_gross=1000)
        cls.mine = add_holding(domain=domain, kind=kind, name="North Shaft")
        cls.farm = add_holding(domain=domain, kind=kind, name="South Fields")
        HoldingMaterialSourceFactory(
            holding=cls.mine,
            material_category=MaterialCategoryFactory(name="Semiprecious"),
            source_kind=MaterialSourceKind.GEM_MINE,
        )

    def test_only_configured_holdings_accrue(self) -> None:
        with patch("world.items.materials_production.accrue_holding_materials") as mock_accrue:
            count = _weekly_mine_accrual()
        self.assertEqual(count, 1)  # the farm (no material source) doesn't accrue
        mock_accrue.assert_called_once_with(holding=self.mine)

    def test_one_broken_holding_never_wedges_the_rollover(self) -> None:
        HoldingMaterialSourceFactory(
            holding=self.farm,
            material_category=MaterialCategoryFactory(name="Precious"),
            source_kind=MaterialSourceKind.GEM_MINE,
        )
        with patch(
            "world.items.materials_production.accrue_holding_materials",
            side_effect=[RuntimeError("boom"), None],
        ) as mock_accrue:
            count = _weekly_mine_accrual()
        self.assertEqual(count, 1)  # the healthy one still ran
        self.assertEqual(mock_accrue.call_count, 2)

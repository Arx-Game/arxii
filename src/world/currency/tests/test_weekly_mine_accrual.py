"""Weekly mine accrual rides the economy rollover (#2540 Build 0b wiring)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.currency.services import _weekly_mine_accrual
from world.items.factories import MaterialCategoryFactory
from world.societies.factories import OrganizationFactory
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
        cls.mine.common_gem_tier = MaterialCategoryFactory(name="Semiprecious")
        cls.mine.save(update_fields=["common_gem_tier"])

    def test_only_configured_mines_accrue(self) -> None:
        with patch("world.items.gems.mining.accrue_mine_cycle") as mock_accrue:
            count = _weekly_mine_accrual()
        self.assertEqual(count, 1)  # the farm (no gem tier) is not a mine
        mock_accrue.assert_called_once_with(holding=self.mine)

    def test_one_broken_holding_never_wedges_the_rollover(self) -> None:
        other = self.farm
        other.common_gem_tier = MaterialCategoryFactory(name="Precious")
        other.save(update_fields=["common_gem_tier"])
        with patch(
            "world.items.gems.mining.accrue_mine_cycle", side_effect=[RuntimeError("boom"), None]
        ) as mock_accrue:
            count = _weekly_mine_accrual()
        self.assertEqual(count, 1)  # the healthy one still ran
        self.assertEqual(mock_accrue.call_count, 2)

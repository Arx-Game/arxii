from decimal import Decimal

from django.test import TestCase

from world.magic.models import TechniqueBudgetConfig, TechniqueTierBudget


class TechniqueBudgetModelTests(TestCase):
    def test_config_defaults(self):
        cfg = TechniqueBudgetConfig.objects.create(pk=1)
        assert cfg.intensity_unit_cost == 1
        assert cfg.payload_base_cost == 2
        assert cfg.restriction_refund_multiplier == Decimal("1.0")

    def test_tier_budget_unique_tier(self):
        TechniqueTierBudget.objects.create(
            tier=1, power_budget=20, representative_level=1, label="Tier 1"
        )
        row = TechniqueTierBudget.objects.get(tier=1)
        assert row.power_budget == 20
        assert row.representative_level == 1

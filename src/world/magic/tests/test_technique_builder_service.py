from django.test import TestCase

from world.magic.models import TechniqueBudgetConfig, TechniqueTierBudget
from world.magic.services.technique_builder import (
    get_technique_budget_config,
    get_technique_tier_budget,
)


class ConfigAccessorTests(TestCase):
    def test_config_lazy_created(self):
        assert TechniqueBudgetConfig.objects.count() == 0
        cfg = get_technique_budget_config()
        assert cfg.pk == 1
        assert TechniqueBudgetConfig.objects.count() == 1

    def test_tier_budget_lazy_defaults(self):
        row = get_technique_tier_budget(3)
        assert row.tier == 3
        assert row.power_budget == 60
        assert row.representative_level == 11
        assert TechniqueTierBudget.objects.get(tier=3).pk == row.pk

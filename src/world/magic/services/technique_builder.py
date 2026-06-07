"""Budget-based technique builder services (#537): config accessors,
pricing, authoring policies, and the build/author entry points."""

from __future__ import annotations

from django.db import transaction

from world.magic.models import TechniqueBudgetConfig, TechniqueTierBudget

DEFAULT_TIER_POWER_BUDGET = {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}
DEFAULT_TIER_REPRESENTATIVE_LEVEL = {1: 1, 2: 6, 3: 11, 4: 16, 5: 21}


def get_technique_budget_config() -> TechniqueBudgetConfig:
    """Get-or-create the budget config singleton (pk=1)."""
    with transaction.atomic():
        cfg, _ = TechniqueBudgetConfig.objects.get_or_create(pk=1)
        return cfg


def get_technique_tier_budget(tier: int) -> TechniqueTierBudget:
    """Get-or-create the per-tier budget row, seeding sane defaults."""
    with transaction.atomic():
        row, _ = TechniqueTierBudget.objects.get_or_create(
            tier=tier,
            defaults={
                "power_budget": DEFAULT_TIER_POWER_BUDGET.get(tier, 20 * tier),
                "representative_level": DEFAULT_TIER_REPRESENTATIVE_LEVEL.get(
                    tier, 1 + (tier - 1) * 5
                ),
                "label": f"Tier {tier}",
            },
        )
        return row

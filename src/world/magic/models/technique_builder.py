"""Staff-tunable config for the budget-based technique builder (#537).

TechniqueBudgetConfig is a singleton of power-cost-per-unit knobs.
TechniqueTierBudget is the per-tier reference power budget + the level
stamped on techniques authored at that tier. Both are advisory for staff
and enforced for players/GMs by the AuthoringPolicy layer.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class TechniqueBudgetConfig(SharedMemoryModel):
    """Singleton (pk=1) of power-cost-per-unit knobs. Access via
    ``get_technique_budget_config()`` in ``services/technique_builder.py``."""

    intensity_unit_cost = models.PositiveIntegerField(default=1)
    control_unit_cost = models.PositiveIntegerField(default=1)
    capability_value_unit_cost = models.PositiveIntegerField(default=1)
    damage_unit_cost = models.PositiveIntegerField(default=1)
    condition_severity_unit_cost = models.PositiveIntegerField(default=1)
    condition_duration_unit_cost = models.PositiveIntegerField(default=1)
    payload_base_cost = models.PositiveIntegerField(
        default=2, help_text="Flat power cost charged per payload row."
    )
    restriction_refund_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Budget credit per point of Restriction.power_bonus.",
    )

    class Meta:
        verbose_name = "Technique Budget Config"
        verbose_name_plural = "Technique Budget Configs"

    def __str__(self) -> str:
        return f"TechniqueBudgetConfig(payload_base={self.payload_base_cost})"


class TechniqueTierBudget(SharedMemoryModel):
    """Per-tier reference power budget + representative level. One row per tier."""

    tier = models.PositiveSmallIntegerField(unique=True)
    power_budget = models.PositiveIntegerField(
        help_text="Reference power for the tier; enforced for players, advisory for staff.",
    )
    representative_level = models.PositiveSmallIntegerField(
        help_text="Level stamped on techniques authored at this tier (derives Technique.tier).",
    )
    label = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ("tier",)
        verbose_name = "Technique Tier Budget"
        verbose_name_plural = "Technique Tier Budgets"

    def __str__(self) -> str:
        return f"Tier {self.tier} (budget {self.power_budget})"

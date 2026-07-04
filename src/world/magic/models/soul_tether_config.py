"""SoulTetherConfig — singleton tuning surface for the Soul Tether bond mechanic (Spec B)."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager


class SoulTetherConfig(SharedMemoryModel):
    """Singleton tuning surface (pk=1).

    All integer fields; multipliers encoded as integer-tenths or integer-hundredths
    to avoid float precision. Access via ``get_soul_tether_config()`` — singleton-by-
    convention, no DB-level uniqueness constraint.

    Sineating fields:
    - ``anima_cost_per_unit``: Sineater anima cost per unit eaten (default 2).
    - ``fatigue_cost_per_unit``: Sineater fatigue cost per unit eaten (default 1).
    - ``per_scene_cap_hard_max``: Hard ceiling on units accepted per scene (default 20).
    - ``per_scene_cap_level_mult``: Hollow-level multiplier for the per-scene cap (default 2).
    - ``per_scene_cap_base``: Base per-scene cap before level scaling (default 5).
    - ``hollow_max_level_mult``: Multiplier on Hollow-level for max Hollow capacity (default 10).

    Rescue thresholds (minimum Hollow strain to trigger each stage):
    - ``rescue_strain_stage3`` / ``_stage4`` / ``_stage5``: strain thresholds (5/10/18).

    Rescue resonance costs:
    - ``rescue_resonance_stage3`` / ``_stage4`` / ``_stage5``: resonance cost (10/20/35).

    Rescue budget bases:
    - ``rescue_budget_base_stage3`` / ``_stage4`` / ``_stage5``: budget base (60/120/250).

    Rescue budget multipliers (formula = base/10 + success * success/10 + thread * thread/100):
    - ``rescue_budget_base_mult_tenths``: base multiplier in tenths (default 10 → 1.0).
    - ``rescue_budget_success_mult_tenths``: success-level multiplier in tenths (default 5 → 0.5).
    - ``rescue_budget_thread_mult_hundredths``: thread-level multiplier in hundredths (5 → 0.05).
    """

    objects = ArxSharedMemoryManager()

    # --- Sineating ---
    anima_cost_per_unit = models.PositiveSmallIntegerField(default=2)
    fatigue_cost_per_unit = models.PositiveSmallIntegerField(default=1)
    per_scene_cap_hard_max = models.PositiveSmallIntegerField(default=20)
    per_scene_cap_level_mult = models.PositiveSmallIntegerField(default=2)
    per_scene_cap_base = models.PositiveSmallIntegerField(default=5)
    hollow_max_level_mult = models.PositiveSmallIntegerField(default=10)

    # --- Rescue strain thresholds ---
    rescue_strain_stage3 = models.PositiveSmallIntegerField(default=5)
    rescue_strain_stage4 = models.PositiveSmallIntegerField(default=10)
    rescue_strain_stage5 = models.PositiveSmallIntegerField(default=18)

    # --- Rescue resonance costs ---
    rescue_resonance_stage3 = models.PositiveSmallIntegerField(default=10)
    rescue_resonance_stage4 = models.PositiveSmallIntegerField(default=20)
    rescue_resonance_stage5 = models.PositiveSmallIntegerField(default=35)

    # --- Rescue budget bases ---
    rescue_budget_base_stage3 = models.PositiveSmallIntegerField(default=60)
    rescue_budget_base_stage4 = models.PositiveSmallIntegerField(default=120)
    rescue_budget_base_stage5 = models.PositiveSmallIntegerField(default=250)

    # --- Rescue budget multipliers (integer-encoded) ---
    # Reconstruct as: base/10 + success * success_tenths/10 + thread * thread_hundredths/100
    rescue_budget_base_mult_tenths = models.PositiveSmallIntegerField(
        default=10,
        help_text="Base budget multiplier in tenths (10 → 1.0).",
    )
    rescue_budget_success_mult_tenths = models.PositiveSmallIntegerField(
        default=5,
        help_text="Per-success-level budget multiplier in tenths (5 → 0.5).",
    )
    rescue_budget_thread_mult_hundredths = models.PositiveSmallIntegerField(
        default=5,
        help_text="Per-thread-level budget multiplier in hundredths (5 → 0.05).",
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="soul_tether_config_updates",
    )

    def __str__(self) -> str:
        return f"SoulTetherConfig(pk={self.pk})"

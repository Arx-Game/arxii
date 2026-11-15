"""SoulTetherConfig — singleton tuning surface for the Soul Tether bond mechanic (Spec B)."""

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class SoulTetherConfig(NaturalKeyMixin, SharedMemoryModel):
    """Singleton tuning surface (pk=1).

    All integer fields; multipliers encoded as integer-tenths or integer-hundredths
    to avoid float precision. Access via ``get_soul_tether_config()`` — singleton-by-
    convention, no DB-level uniqueness constraint.

    Sineating fields:
    - ``anima_cost_per_unit``: Sineater anima cost per unit eaten (default 2).
    - ``fatigue_cost_per_unit``: Sineater fatigue cost per unit eaten (default 1).
    - ``per_scene_cap_hard_max``: Hard ceiling on units accepted per scene (default 20).
    - ``per_scene_cap_base``: Base per-scene cap before level scaling (default 5).

    The level scaling of the per-scene cap and of the Hollow's maximum capacity is the
    ``SOUL_TETHER_SCENE_CAP`` and ``HOLLOW_MAX`` lanes' ``ModifierLevelBaseline`` rows, one per
    rung (10 thread levels), seeded at 2 and 10 per rung (#5093).

    Rescue thresholds (minimum Hollow strain to trigger each stage):
    - ``rescue_strain_stage3`` / ``_stage4`` / ``_stage5``: strain thresholds (5/10/18).

    Rescue resonance costs:
    - ``rescue_resonance_stage3`` / ``_stage4`` / ``_stage5``: resonance cost (10/20/35).

    Rescue budget bases:
    - ``rescue_budget_base_stage3`` / ``_stage4`` / ``_stage5``: budget base (60/120/250).

    Rescue budget multipliers (formula = base/10 + success * success/10 + thread rung term):
    - ``rescue_budget_base_mult_tenths``: base multiplier in tenths (default 10 → 1.0).
    - ``rescue_budget_success_mult_tenths``: success-level multiplier in tenths (default 5 → 0.5).
    - The thread term is the ``RESCUE_BUDGET_THREAD`` lane's baseline at the Sineater's thread
      rung, in hundredths (#5093; the seeded rows give 0.5 a rung, what 0.05 a thread level did).
    """

    class NaturalKeyConfig:
        fields = ["pk"]

    objects = NaturalKeyManager()

    # --- Sineating ---
    anima_cost_per_unit = models.PositiveSmallIntegerField(default=2)
    fatigue_cost_per_unit = models.PositiveSmallIntegerField(default=1)
    per_scene_cap_hard_max = models.PositiveSmallIntegerField(default=20)
    per_scene_cap_base = models.PositiveSmallIntegerField(default=5)

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
    # Reconstruct as: base/10 + success * success_tenths/10 + the thread rung lane's term
    rescue_budget_base_mult_tenths = models.PositiveSmallIntegerField(
        default=10,
        help_text="Base budget multiplier in tenths (10 → 1.0).",
    )
    rescue_budget_success_mult_tenths = models.PositiveSmallIntegerField(
        default=5,
        help_text="Per-success-level budget multiplier in tenths (5 → 0.5).",
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

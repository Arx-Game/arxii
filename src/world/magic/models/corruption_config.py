"""CorruptionConfig — singleton tuning surface for the Corruption foundation."""

from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel


class CorruptionConfig(SharedMemoryModel):
    """Singleton tuning surface (pk=1).

    All coefficients are integer-tenths (× 0.1 in formula) to avoid float
    precision. Mirrors SoulfrayConfig and ResonanceGainConfig patterns.
    """

    objects = ArxSharedMemoryManager()

    tier_1_coefficient = models.PositiveSmallIntegerField(default=10)
    tier_2_coefficient = models.PositiveSmallIntegerField(default=20)
    tier_3_coefficient = models.PositiveSmallIntegerField(default=40)
    tier_4_coefficient = models.PositiveSmallIntegerField(default=80)
    tier_5_coefficient = models.PositiveSmallIntegerField(default=160)

    deficit_multiplier = models.PositiveSmallIntegerField(default=20)
    mishap_multiplier = models.PositiveSmallIntegerField(default=15)
    audere_multiplier = models.PositiveSmallIntegerField(default=15)
    hasty_fall_multiplier = models.PositiveSmallIntegerField(
        default=20,
        help_text=(
            "Integer tenths multiplying a cast's corruption tick when an Abyssal caster "
            "burns Celestial or Primal resonance (a hasty fall). 20 = 2.0x."
        ),
    )
    alternate_self_base_leak_percent = models.PositiveSmallIntegerField(
        default=10,
        help_text=(
            "Starting share of an active alternate self's cast corruption that reaches "
            "the player character. The rest is absorbed by the separate identity."
        ),
    )
    alternate_self_leak_percent_per_success_level = models.PositiveSmallIntegerField(
        default=2,
        help_text=(
            "Percentage points by which each success level reduces alternate-self cast "
            "corruption reaching the player character. Failures increase it."
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="corruption_config_updates",
    )

    def __str__(self) -> str:
        return f"CorruptionConfig(pk={self.pk})"

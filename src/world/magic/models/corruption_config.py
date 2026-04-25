"""CorruptionConfig — singleton tuning surface for the Corruption foundation."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class CorruptionConfig(SharedMemoryModel):
    """Singleton tuning surface (pk=1).

    All coefficients are integer-tenths (× 0.1 in formula) to avoid float
    precision. Mirrors SoulfrayConfig and ResonanceGainConfig patterns.
    """

    celestial_coefficient = models.PositiveSmallIntegerField(default=0)
    primal_coefficient = models.PositiveSmallIntegerField(default=2)
    abyssal_coefficient = models.PositiveSmallIntegerField(default=10)

    tier_1_coefficient = models.PositiveSmallIntegerField(default=10)
    tier_2_coefficient = models.PositiveSmallIntegerField(default=20)
    tier_3_coefficient = models.PositiveSmallIntegerField(default=40)
    tier_4_coefficient = models.PositiveSmallIntegerField(default=80)
    tier_5_coefficient = models.PositiveSmallIntegerField(default=160)

    deficit_multiplier = models.PositiveSmallIntegerField(default=20)
    mishap_multiplier = models.PositiveSmallIntegerField(default=15)
    audere_multiplier = models.PositiveSmallIntegerField(default=15)

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

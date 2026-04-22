"""Soulfray configuration and mishap pools.

SoulfrayConfig is the global single-row config for Soulfray severity
accumulation and resilience checks.
MishapPoolTier maps control-deficit ranges to consequence pools for
imprecision mishaps.
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class SoulfrayConfig(SharedMemoryModel):
    """Global configuration for Soulfray severity accumulation and resilience checks.

    Single-row table (queried with .first()), same pattern as AudereThreshold.
    """

    soulfray_threshold_ratio = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text=(
            "Anima ratio (current/max) below which technique use "
            "accumulates Soulfray severity. E.g., 0.30 = below 30%%."
        ),
    )
    severity_scale = models.PositiveIntegerField(
        help_text="Base scaling factor for converting depletion into severity.",
    )
    deficit_scale = models.PositiveIntegerField(
        help_text="Additional scaling factor for deficit (anima spent beyond zero).",
    )
    resilience_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        help_text="Check type for Soulfray resilience (e.g., magical endurance).",
    )
    base_check_difficulty = models.PositiveIntegerField(
        help_text="Base difficulty for the resilience check before stage modifiers.",
    )

    class Meta:
        verbose_name = "Soulfray Configuration"
        verbose_name_plural = "Soulfray Configurations"

    def __str__(self) -> str:
        return (
            f"SoulfrayConfig(threshold={self.soulfray_threshold_ratio}, "
            f"scale={self.severity_scale})"
        )


class MishapPoolTier(SharedMemoryModel):
    """Maps control deficit ranges to consequence pools for imprecision mishaps.

    Ranges must not overlap. Validated via clean().
    Control mishap pools must never contain character_loss consequences.
    """

    min_deficit = models.PositiveIntegerField(
        help_text="Minimum control deficit for this tier (inclusive).",
    )
    max_deficit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum control deficit for this tier (inclusive). Null = no upper bound.",
    )
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.CASCADE,
        related_name="mishap_tiers",
        help_text="Consequence pool for this deficit range.",
    )

    def __str__(self) -> str:
        upper = self.max_deficit or "∞"
        return f"Mishap {self.min_deficit}-{upper}"

    def clean(self) -> None:
        """Validate that this tier's range does not overlap with existing tiers."""
        overlapping = MishapPoolTier.objects.exclude(pk=self.pk)
        if self.max_deficit is not None:
            overlapping = overlapping.filter(
                min_deficit__lte=self.max_deficit,
            ).exclude(
                max_deficit__isnull=False,
                max_deficit__lt=self.min_deficit,
            )
        else:
            overlapping = overlapping.exclude(
                max_deficit__isnull=False,
                max_deficit__lt=self.min_deficit,
            )
        if overlapping.exists():
            msg = "Deficit range overlaps with an existing MishapPoolTier."
            raise ValidationError(msg)

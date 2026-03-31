"""Audere threshold configuration and lifecycle management."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class AudereThreshold(SharedMemoryModel):
    """Configuration for when Audere can be triggered and its effects.

    Expected to have a single row (global config). Modeled as a table
    for factory/test flexibility and admin editability.

    Audere requires a hard triple gate:
    1. Runtime intensity at or above minimum_intensity_tier
    2. Active Anima Warp condition at or above minimum_warp_stage
    3. Active CharacterEngagement (character must be in stakes)
    """

    minimum_intensity_tier = models.ForeignKey(
        "magic.IntensityTier",
        on_delete=models.PROTECT,
        help_text="Runtime intensity must reach this tier for Audere to trigger.",
    )
    minimum_warp_stage = models.ForeignKey(
        "conditions.ConditionStage",
        on_delete=models.PROTECT,
        help_text="Anima Warp must be at this stage or higher.",
    )
    intensity_bonus = models.IntegerField(
        help_text="Added to engagement.intensity_modifier when Audere activates.",
    )
    anima_pool_bonus = models.PositiveIntegerField(
        help_text="Temporary increase to CharacterAnima.maximum during Audere.",
    )
    warp_multiplier = models.PositiveIntegerField(
        default=2,
        help_text="Warp severity increment multiplier during Audere.",
    )

    class Meta:
        verbose_name = "Audere Threshold"
        verbose_name_plural = "Audere Thresholds"

    def __str__(self) -> str:
        return (
            f"Audere: tier≥{self.minimum_intensity_tier}, "
            f"warp≥{self.minimum_warp_stage}, "
            f"+{self.intensity_bonus} intensity"
        )

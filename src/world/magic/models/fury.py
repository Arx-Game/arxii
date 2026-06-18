"""Fury lever models: FuryTier (authored depth catalog) and FuryConfig (singleton tuning)."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.constants import FuryCheckTrait


class FuryTier(NaturalKeyMixin, SharedMemoryModel):
    """Authored, player-chosen depth of giving in to rage. Analogous in shape to
    IntensityTier but selected by the player, not by channeled power."""

    name = models.CharField(max_length=50, unique=True)
    depth = models.PositiveSmallIntegerField(
        unique=True, help_text="Tier depth; compared against the provocation cap."
    )
    control_penalty = models.PositiveSmallIntegerField(
        default=0, help_text="Amount subtracted from runtime control at this tier."
    )
    intensity_bonus = models.PositiveSmallIntegerField(
        default=0, help_text="Base intensity/power bonus (scaled by provocation)."
    )
    base_check_difficulty = models.IntegerField(
        default=0, help_text="Base control-retention check difficulty before provocation ease."
    )
    lucid_grade_floor = models.PositiveSmallIntegerField(
        default=1, help_text="Min CheckResult.success_level to stay lucid (else Berserk)."
    )
    berserk_severity = models.PositiveSmallIntegerField(
        default=0,
        help_text="Berserk condition severity applied on lost control; 0 = never berserk.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["depth"]

    def __str__(self) -> str:
        return f"FuryTier({self.name}, depth={self.depth})"


class FuryConfig(SharedMemoryModel):
    """Singleton (pk=1) tuning surface for the Fury lever (mirrors StrainConfig)."""

    check_trait = models.CharField(
        max_length=32,
        choices=FuryCheckTrait.choices,
        default=FuryCheckTrait.COMPOSURE,
        help_text="Trait rolled for the control-retention check.",
    )
    provocation_cap_per_tier = models.PositiveSmallIntegerField(
        default=1, help_text="Provocation magnitude required per accessible tier of depth."
    )
    bonus_scale_per_cap_point = models.PositiveSmallIntegerField(
        default=10, help_text="Percent the intensity bonus grows per point of provocation cap."
    )
    cap_ease_per_point = models.PositiveSmallIntegerField(
        default=1, help_text="Check difficulty reduction per point of provocation cap."
    )
    default_berserk_duration_rounds = models.PositiveSmallIntegerField(
        default=3, help_text="Default rounds_remaining for an applied Berserk condition."
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"FuryConfig(pk={self.pk})"

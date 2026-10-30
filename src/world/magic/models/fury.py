"""Fury lever models: FuryTier (authored depth catalog), FuryConfig (singleton tuning) and
FuryDegreeShare (how much of the trade each outcome of the control roll buys)."""

from django.core.exceptions import ValidationError
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.checks.models import OutcomeTierAward
from world.magic.constants import FuryCheckTrait


class FuryTier(NaturalKeyMixin, SharedMemoryModel):
    """Authored, player-chosen depth of giving in to rage (#4738).

    Each tier is a preset amount of control the character surrenders for the rest of her
    engagement; the control roll's outcome sets how much intensity that buys
    (``FuryDegreeShare``). The deepest tiers carry ``berserk_severity`` and are Berserk:
    chosen, never rolled into."""

    name = models.CharField(max_length=50, unique=True)
    depth = models.PositiveSmallIntegerField(
        unique=True, help_text="Tier depth; compared against the provocation cap."
    )
    control_surrendered = models.PositiveSmallIntegerField(
        default=0, help_text="Control this tier gives up for the rest of the engagement."
    )
    base_check_difficulty = models.IntegerField(
        default=0, help_text="Base control-retention check difficulty before provocation ease."
    )
    berserk_severity = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Above 0 makes this the Berserk tier: choosing it always applies Berserk at this "
            "severity. 0 = not Berserk."
        ),
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

    objects = ArxSharedMemoryManager()

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
        default=10,
        help_text="Percent the intensity Fury buys grows per point of provocation cap.",
    )
    cap_ease_per_point = models.PositiveSmallIntegerField(
        default=1, help_text="Check difficulty reduction per point of provocation cap."
    )
    default_berserk_duration_rounds = models.PositiveSmallIntegerField(
        default=3, help_text="Default rounds_remaining for an applied Berserk condition."
    )
    berserk_condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The condition template that IS Berserk (#4739). Lost Fury control and "
            "moon-sensitivity fury apply it, and the rampage compulsion finds it, through "
            "this field, so renaming the template changes nothing. The Required content "
            "dashboard flags it unset."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"FuryConfig(pk={self.pk})"


class FuryDegreeShare(OutcomeTierAward):
    """Percent of the full Fury trade the control roll buys at one outcome tier (#4738).

    The full trade is ``control_surrendered x StrainConfig.intensity_per_control_surrendered``,
    scaled up by the anchor's provocation cap. An outcome tier with no row buys nothing (0%);
    the Required content dashboard lists the missing tiers.

    A better outcome never buys a smaller percent than a worse one; ``clean`` enforces it.
    """

    intensity_percent = models.PositiveSmallIntegerField(
        help_text="Percent of the full trade the Fury control roll buys at this outcome."
    )

    class Meta(OutcomeTierAward.Meta):
        verbose_name = "Fury degree share"

    def __str__(self) -> str:
        return f"{self.outcome_tier_id}: {self.intensity_percent}%"

    def clean(self) -> None:
        super().clean()
        if self.intensity_percent is None or self.outcome_tier_id is None:
            return
        siblings = type(self).objects.exclude(pk=self.pk)
        level = self.outcome_tier.success_level
        worse_above = siblings.filter(
            outcome_tier__success_level__lt=level, intensity_percent__gt=self.intensity_percent
        ).exists()
        better_below = siblings.filter(
            outcome_tier__success_level__gt=level, intensity_percent__lt=self.intensity_percent
        ).exists()
        if worse_above or better_below:
            raise ValidationError(
                {"intensity_percent": "A better outcome must buy at least as much as a worse one."}
            )

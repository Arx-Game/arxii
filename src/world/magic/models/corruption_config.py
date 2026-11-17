"""CorruptionConfig — singleton tuning surface for the Corruption foundation."""

from django.core.exceptions import ValidationError
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

    intrusive_thoughts_stage = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "The corruption stage at which a character carrying corruption in a resonance "
            "begins to feel its impulse: the condition reads 'Intrusive Thoughts: <resonance>' "
            "and, when something that resonance cares about is present in a scene, they are "
            "sent the resonance's impulse text once."
        ),
    )
    compulsion_stage = models.PositiveSmallIntegerField(
        default=2,
        help_text=(
            "The corruption stage at which the impulse becomes a Compulsion: the condition "
            "reads 'Compulsion: <resonance>' and, when something that resonance cares about "
            "is present in a scene, the Compulsion condition penalizes the character's rolls "
            "until they earn that resonance there."
        ),
    )
    sineater_max_stage = models.PositiveSmallIntegerField(
        default=2,
        help_text=(
            "The corruption stage a Sineater's carried corruption stops at. Sineating takes on "
            "only what fits below the top of this stage and refuses when nothing fits. "
            "Normally the Compulsion stage."
        ),
    )
    compulsion_condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The condition laid on a character at the Compulsion stage while something their "
            "resonance cares about is present. Give it a scene duration and a check modifier "
            "that scales with severity. Unset applies nothing and the Required content page "
            "lists it."
        ),
    )
    compulsion_indulge_corruption = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Corruption added in the resonance when a character under a Compulsion gives in "
            "by earning that resonance in the scene. The Compulsion lifts for the scene."
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

    def clean(self) -> None:
        """A Sineater's cap cannot sit below the stage where impulses begin."""
        super().clean()
        if self.sineater_max_stage < self.intrusive_thoughts_stage:
            msg = {
                "sineater_max_stage": (
                    "A Sineater's cap cannot be below the stage where Intrusive Thoughts begin."
                )
            }
            raise ValidationError(msg)

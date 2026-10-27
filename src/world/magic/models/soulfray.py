"""Soulfray configuration and mishap pools.

SoulfrayConfig is the global single-row config for Soulfray severity
accumulation and resilience checks.
MishapPoolTier maps control-deficit ranges to consequence pools for
imprecision mishaps.
"""

from django.core.exceptions import ValidationError
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.checks.models import OutcomeTierAward


class SoulfrayConfig(SharedMemoryModel):
    """Global configuration for Soulfray severity accumulation and resilience checks.

    Single-row table (queried via cached_singleton()), same pattern as AudereThreshold.
    """

    objects = ArxSharedMemoryManager()

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
        "arxii.CheckType",
        on_delete=models.PROTECT,
        help_text="Check type for Soulfray resilience (e.g., magical endurance).",
    )
    base_check_difficulty = models.PositiveIntegerField(
        help_text="Base difficulty for the resilience check before stage modifiers.",
    )
    ritual_severity_cost_per_point = models.PositiveIntegerField(default=1)
    social_safety_bonus = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Control bonus applied to a character's technique control when they are "
            "not currently engaged in combat (no active CharacterEngagement row). "
            "Raising this lowers the effective anima cost of casting outside a fight "
            "(see calculate_effective_anima_cost's control-delta formula) — at a high "
            "enough value, social/out-of-combat casting costs barely any anima."
        ),
    )

    condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The condition template that IS Soulfray. Every Soulfray rule (accrual, "
            "the non-lethal cap, the safety checkpoint warning, the Soulfray Stage "
            "Builder, Audere eligibility) finds Soulfray through this field, so "
            "renaming the template changes nothing. Leave unset only before Soulfray "
            "is authored; the Required content dashboard flags an unset value."
        ),
    )
    anima_zero_stage = models.ForeignKey(
        "arxii.ConditionStage",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "While she has anima left, Soulfray cannot advance into this stage or "
            "beyond; it needs anima at 0."
        ),
    )

    class Meta:
        verbose_name = "Soulfray Configuration"
        verbose_name_plural = "Soulfray Configurations"

    def __str__(self) -> str:
        return (
            f"SoulfrayConfig(threshold={self.soulfray_threshold_ratio}, "
            f"scale={self.severity_scale})"
        )

    def clean(self) -> None:
        """The anima-0 stage must be a severity stage of the Soulfray template (#4740)."""
        super().clean()
        stage = self.anima_zero_stage
        if stage is None:
            return
        if stage.condition_id != self.condition_id:
            raise ValidationError(
                {"anima_zero_stage": "Pick a stage of the Soulfray condition set above."}
            )
        if stage.severity_threshold is None:
            raise ValidationError(
                {
                    "anima_zero_stage": (
                        "This stage has no severity threshold, so severity never reaches "
                        "it and the anima-0 rule would do nothing."
                    )
                }
            )

    def anima_zero_ceiling(self, current_anima: int) -> int | None:
        """Highest Soulfray severity reachable with ``current_anima`` left (#4740).

        ``anima_zero_stage.severity_threshold - 1`` while she still has anima; ``None``
        (no cap) at anima 0, or when no anima-0 stage with a threshold is set.
        """
        stage = self.anima_zero_stage
        if current_anima <= 0 or stage is None or stage.severity_threshold is None:
            return None
        return max(stage.severity_threshold - 1, 0)


class MishapPoolTier(SharedMemoryModel):
    """Maps control deficit ranges to consequence pools for imprecision mishaps.

    Ranges must not overlap. Validated via clean().
    Control mishap pools must never contain character_loss consequences.
    """

    objects = ArxSharedMemoryManager()

    min_deficit = models.PositiveIntegerField(
        help_text="Minimum control deficit for this tier (inclusive).",
    )
    max_deficit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum control deficit for this tier (inclusive). Null = no upper bound.",
    )
    consequence_pool = models.ForeignKey(
        "arxii.ConsequencePool",
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


class AnimaRitualBudgetAward(OutcomeTierAward):
    """Anima/severity budget granted by the personal anima-recovery ritual, per tier.

    Replaces the old SoulfrayConfig.ritual_budget_critical_success/_success/_partial/
    _failure fields and anima.py's private _CRIT_SUCCESS_LEVEL/_SUCCESS_LEVEL/
    _PARTIAL_LEVEL constants (#1207) — those re-derived the canonical CheckOutcome
    spine instead of matching it directly, and disagreed with ritual_checks.OutcomeTier
    about what success_level == 0 meant. Every one of the 5 canonical tiers must have
    an authored row (unlike GangTurfReputationAward's "missing = 0" convention) —
    _budget_for_outcome (anima.py) raises clearly rather than silently granting 0
    anima on an un-seeded tier.
    """

    budget = models.PositiveIntegerField(
        help_text="Anima/severity budget granted for this outcome tier.",
    )
